import bisect
import json
import math
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytorch_lightning as pl
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset, IterableDataset

import threestudio
from threestudio import register
from threestudio.data.uncond import (
    RandomCameraDataModuleConfig,
    RandomCameraDataset,
    RandomCameraIterableDataset,
)
from threestudio.utils.base import Updateable
from threestudio.utils.config import parse_structured
from threestudio.utils.misc import get_rank
from threestudio.utils.ops import (
    get_mvp_matrix,
    get_projection_matrix,
    get_ray_directions,
    get_rays,
)
from threestudio.utils.typing import *


@dataclass
class MultiImageDataModuleConfig:
    # height and width should be Union[int, List[int]]
    # but OmegaConf does not support Union of containers
    transform_fp: str = ""
    image_paths: List[str] = field(default_factory=lambda: [])

    height: Any = 96
    width: Any = 96
    resolution_milestones: List[int] = field(default_factory=lambda: [])
    default_elevation_degs: List[float] = field(default_factory=lambda: [])
    default_azimuth_degs: List[float] = field(default_factory=lambda: [])
    default_camera_distances: List[float] = field(default_factory=lambda: [])

    default_elevation_deg: float = 0.0
    default_camera_distance: float = 3.8
    default_fovy_deg: float = 60.0

    use_random_camera: bool = True
    random_camera: dict = field(default_factory=dict)
    rays_noise_scale: float = 2e-3
    batch_size: int = 1
    requires_depth: bool = False
    requires_normal: bool = False


class MultiImageDataBase:
    def setup(self, cfg, split):
        self.split = split
        self.rank = get_rank()
        self.cfg: MultiImageDataModuleConfig = cfg
        self.load_transform(self.cfg.transform_fp)

        if self.cfg.use_random_camera:
            random_camera_cfg = parse_structured(
                RandomCameraDataModuleConfig, self.cfg.get("random_camera", {})
            )
            if split == "train":
                self.random_pose_generator = RandomCameraIterableDataset(
                    random_camera_cfg
                )
            else:
                self.random_pose_generator = RandomCameraDataset(
                    random_camera_cfg, split
                )

        elevation_degs = torch.FloatTensor([self.cfg.default_elevation_degs])
        azimuth_degs = torch.FloatTensor([self.cfg.default_azimuth_degs])
        camera_distances = torch.FloatTensor([self.cfg.default_camera_distances])

        elevations = elevation_degs * math.pi / 180
        azimuths = azimuth_degs * math.pi / 180
        camera_positions: Float[Tensor, "B 3"] = torch.cat(
            [
                camera_distances * torch.cos(elevations) * torch.cos(azimuths),
                camera_distances * torch.cos(elevations) * torch.sin(azimuths),
                camera_distances * torch.sin(elevations),
            ],
        ).T

        center: Float[Tensor, "1 3"] = torch.zeros_like(camera_positions[[0]])
        up: Float[Tensor, "1 3"] = torch.as_tensor([0, 0, 1], dtype=torch.float32)[None]

        light_position: Float[Tensor, "1 3"] = camera_positions[[0]]
        lookat: Float[Tensor, "B 3"] = F.normalize(center - camera_positions, dim=-1)
        right: Float[Tensor, "B 3"] = F.normalize(torch.cross(lookat, up), dim=-1)
        up = F.normalize(torch.cross(right, lookat), dim=-1)

        self.c2w: Float[Tensor, "B 3 4"] = torch.cat(
            [torch.stack([right, up, -lookat], dim=-1), camera_positions[:, :, None]],
            dim=-1,
        )

        self.camera_positions = camera_positions.squeeze(0)
        self.light_position = light_position
        self.elevation_degs, self.azimuth_degs = elevation_degs.squeeze(
            0
        ), azimuth_degs.squeeze(0)
        self.camera_distances = camera_distances.squeeze(0)
        self.fovy = torch.deg2rad(torch.FloatTensor([self.cfg.default_fovy_deg]))

        self.heights: List[int] = (
            [self.cfg.height] if isinstance(self.cfg.height, int) else self.cfg.height
        )
        self.widths: List[int] = (
            [self.cfg.width] if isinstance(self.cfg.width, int) else self.cfg.width
        )
        assert len(self.heights) == len(self.widths)
        self.resolution_milestones: List[int]
        if len(self.heights) == 1 and len(self.widths) == 1:
            if len(self.cfg.resolution_milestones) > 0:
                threestudio.warn(
                    "Ignoring resolution_milestones since height and width are not changing"
                )
            self.resolution_milestones = [-1]
        else:
            assert len(self.heights) == len(self.cfg.resolution_milestones) + 1
            self.resolution_milestones = [-1] + self.cfg.resolution_milestones

        self.directions_unit_focals = [
            get_ray_directions(H=height, W=width, focal=1.0)
            for (height, width) in zip(self.heights, self.widths)
        ]
        self.focal_lengths = [
            0.5 * height / torch.tan(0.5 * self.fovy) for height in self.heights
        ]

        self.height: int = self.heights[0]
        self.width: int = self.widths[0]
        self.directions_unit_focal = self.directions_unit_focals[0]
        self.focal_length = self.focal_lengths[0]
        self.set_rays()
        self.load_images()
        self.prev_height = self.height

    def load_transform(self, transform_fp: str):
        """Load images from disk."""
        if not transform_fp.startswith("/"):
            # allow relative path
            transform_fp = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../..",
                transform_fp,
            )

        image_dir = os.path.dirname(transform_fp)
        with open(transform_fp, "r") as fp:
            meta = json.load(fp)

        self.cfg.image_paths = []
        self.cfg.default_elevation_degs = []
        self.cfg.default_azimuth_degs = []
        self.cfg.default_camera_distances = []

        for i in range(len(meta["frames"])):
            frame = meta["frames"][i]
            fname = os.path.join(image_dir, frame["file_path"])
            self.cfg.image_paths.append(fname)

            latlon = meta["frames"][i]["latlon"]

            # theta -90 -> bottom, theta 90 -> top in threestudio
            self.cfg.default_elevation_degs.append(
                -latlon[0] + self.cfg.default_elevation_deg
            )
            self.cfg.default_azimuth_degs.append(latlon[1])
            self.cfg.default_camera_distances.append(latlon[2])

        # scale camera distances to avoid OOM
        scale_factor = (
            self.cfg.default_camera_distance / min(self.cfg.default_camera_distances)
        )
        self.cfg.default_camera_distances = [
            float(d * scale_factor) for d in self.cfg.default_camera_distances
        ]

    def set_rays(self):
        # get directions by dividing directions_unit_focal by focal length
        directions: Float[Tensor, "1 H W 3"] = self.directions_unit_focal[None]
        directions[:, :, :, :2] = directions[:, :, :, :2] / self.focal_length

        rays_o, rays_d = get_rays(
            directions, self.c2w, keepdim=True, noise_scale=self.cfg.rays_noise_scale
        )

        proj_mtx: Float[Tensor, "4 4"] = get_projection_matrix(
            self.fovy, self.width / self.height, 0.1, 100.0
        )  # FIXME: hard-coded near and far
        mvp_mtx: Float[Tensor, "B 4 4"] = get_mvp_matrix(self.c2w, proj_mtx)

        self.rays_o, self.rays_d = rays_o, rays_d
        self.mvp_mtx = mvp_mtx

    def load_images(self):
        # load image
        rgbs, masks, normals, depths = [], [], [], []
        for path in self.cfg.image_paths:
            assert os.path.exists(path), f"Could not find image {path}!"
            rgba = cv2.cvtColor(
                cv2.imread(path, cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA
            )
            rgba = (
                cv2.resize(
                    rgba, (self.width, self.height), interpolation=cv2.INTER_AREA
                ).astype(np.float32)
                / 255.0
            )
            rgb = rgba[..., :3]
            mask = rgba[..., 3:] > 0.5
            rgbs.append(rgb)
            masks.append(mask)
            print(f"[INFO] multi image dataset: load image {path} {rgb.shape}")

            # load depth
            if self.cfg.requires_depth:
                depth_path = path.replace("_rgba.png", "_depth.png")
                assert os.path.exists(depth_path)
                depth = cv2.imread(depth_path, cv2.IMREAD_UNCHANGED)
                depth = cv2.resize(
                    depth, (self.width, self.height), interpolation=cv2.INTER_AREA
                )

                depth = depth.astype(np.float32) / 255.0
                depths.append(depth)
                print(
                    f"[INFO] multi image dataset: load depth {depth_path} {depth.shape}"
                )
            else:
                self.depth = None

            # load normal
            if self.cfg.requires_normal:
                normal_path = path.replace("_rgba.png", "_normal.png")
                assert os.path.exists(normal_path)
                normal = cv2.imread(normal_path, cv2.IMREAD_UNCHANGED)
                normal = cv2.resize(
                    normal, (self.width, self.height), interpolation=cv2.INTER_AREA
                )
                normal = normal.astype(np.float32) / 255.0
                normals.append(normal)
                print(
                    f"[INFO] single image dataset: load normal {normal_path} {normal.shape}"
                )
            else:
                self.normal = None

        self.rgb: Float[Tensor, "B H W 3"] = torch.from_numpy(
            np.stack(rgbs, axis=0)
        ).to(self.rank)
        self.mask: Float[Tensor, "B H W 1"] = torch.from_numpy(
            np.stack(masks, axis=0)
        ).to(self.rank)
        if self.cfg.requires_depth:
            self.depth: Float[Tensor, "B H W 1"] = torch.from_numpy(
                np.stack(depths, axis=0)
            ).to(self.rank)
        if self.cfg.requires_normal:
            self.normal: Float[Tensor, "B H W 3"] = torch.from_numpy(
                np.stack(normals, axis=0)
            ).to(self.rank)

    def get_all_images(self):
        return self.rgb

    def update_step_(self, epoch: int, global_step: int, on_load_weights: bool = False):
        size_ind = bisect.bisect_right(self.resolution_milestones, global_step) - 1
        self.height = self.heights[size_ind]
        if self.height == self.prev_height:
            return

        self.prev_height = self.height
        self.width = self.widths[size_ind]
        self.directions_unit_focal = self.directions_unit_focals[size_ind]
        self.focal_length = self.focal_lengths[size_ind]
        threestudio.debug(f"Training height: {self.height}, width: {self.width}")
        self.set_rays()
        self.load_images()


class MultiImageIterableDataset(IterableDataset, MultiImageDataBase, Updateable):
    def __init__(self, cfg: Any, split: str) -> None:
        super().__init__()
        self.setup(cfg, split)
        self.idx = 0

    def collate(self, batch) -> Dict[str, Any]:
        idx = torch.randint(0, len(self.rgb), (1,))
        batch = {
            "rays_o": self.rays_o[idx],
            "rays_d": self.rays_d[idx],
            "mvp_mtx": self.mvp_mtx[idx],
            "camera_positions": self.camera_positions[idx],
            "light_positions": self.light_position,
            "elevation": self.elevation_degs[idx],
            "azimuth": self.azimuth_degs[idx],
            "camera_distances": self.camera_distances[idx],
            "rgb": self.rgb[idx],
            "ref_depth": None if not self.depth else self.depth[idx],
            "ref_normal": None if not self.depth else self.normal[idx],
            "mask": self.mask[idx],
            "height": self.cfg.height,
            "width": self.cfg.width,
        }
        if self.cfg.use_random_camera:
            batch["random_camera"] = self.random_pose_generator.collate(None)

        return batch

    def update_step(self, epoch: int, global_step: int, on_load_weights: bool = False):
        self.update_step_(epoch, global_step, on_load_weights)
        self.random_pose_generator.update_step(epoch, global_step, on_load_weights)

    def __iter__(self):
        while True:
            yield {}


class MultiImageDataset(Dataset, MultiImageDataBase):
    def __init__(self, cfg: Any, split: str) -> None:
        super().__init__()
        self.setup(cfg, split)

    def __len__(self):
        return len(self.random_pose_generator)

    def __getitem__(self, index):
        return self.random_pose_generator[index]


@register("multi-image-datamodule")
class MultiImageDataModule(pl.LightningDataModule):
    cfg: MultiImageDataModuleConfig

    def __init__(self, cfg: Optional[Union[dict, DictConfig]] = None) -> None:
        super().__init__()
        self.cfg = parse_structured(MultiImageDataModuleConfig, cfg)

    def setup(self, stage=None) -> None:
        if stage in [None, "fit"]:
            self.train_dataset = MultiImageIterableDataset(self.cfg, "train")
        if stage in [None, "fit", "validate"]:
            self.val_dataset = MultiImageDataset(self.cfg, "val")
        if stage in [None, "test", "predict"]:
            self.test_dataset = MultiImageDataset(self.cfg, "test")

    def prepare_data(self):
        pass

    def general_loader(self, dataset, batch_size, collate_fn=None) -> DataLoader:
        return DataLoader(
            dataset, num_workers=0, batch_size=batch_size, collate_fn=collate_fn
        )

    def train_dataloader(self) -> DataLoader:
        return self.general_loader(
            self.train_dataset,
            batch_size=self.cfg.batch_size,
            collate_fn=self.train_dataset.collate,
        )

    def val_dataloader(self) -> DataLoader:
        return self.general_loader(self.val_dataset, batch_size=1)

    def test_dataloader(self) -> DataLoader:
        return self.general_loader(self.test_dataset, batch_size=1)

    def predict_dataloader(self) -> DataLoader:
        return self.general_loader(self.test_dataset, batch_size=1)
