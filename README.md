# iFusion Threestudio

### [Project Page](https://chinhsuanwu.github.io/ifusion) | [Paper](https://arxiv.org/abs/2312.17250)

This code is forked from [threestudio](https://github.com/threestudio-project/threestudio) as an extension of [iFusion](https://github.com/chinhsuanwu/ifusion) for pose-free reconstruction.

<img src="https://github.com/chinhsuanwu/ifusion/assets/67839539/d90bb4a3-f6a6-4121-995f-833c3350c302" width=600><br>

[iFusion: Inverting Diffusion for Pose-Free Reconstruction from Sparse Views]() <br>[Chin-Hsuan Wu](https://chinhsuanwu.github.io),
[Yen-Chun Chen](https://www.microsoft.com/en-us/research/people/yenche/),
[Bolivar Solarte](https://enriquesolarte.github.io/),
[Lu Yuan](https://www.microsoft.com/en-us/research/people/luyuan/),
[Min Sun](https://aliensunmin.github.io/)<br>

## Installation

```bash
git clone https://github.com/chinhsuanwu/ifusion-threestudio.git
cd ifusion-threestudio
```

Skip the following if you have already installed the environment for [threestudio](https://github.com/threestudio-project/threestudio). Please refer to [installation.md](https://github.com/threestudio-project/threestudio/blob/main/docs/installation.md) for detailed information.

```bash
pip install -r requirements.txt
```

Download or link Zero123-XL under `load/zero123`
```bash
cd load/zero123 && wget https://zero123.cs.columbia.edu/assets/zero123-xl.ckpt
```

⚠️ You must have an NVIDIA GPU with at least 20GB VRAM.

## Usage

Run Zero123-SDS by specifing the path to `transform.json` obtained from [iFusion](https://github.com/chinhsuanwu/ifusion)
```bash
python launch.py --config configs/zero123-ifusion.yaml --train --gpu 0 data.transform_fp=path_to_transform.json
```

Run Magic123 with additional text prompt
```bash
python launch.py --config configs/magic123-ifusion-coarse-sd.yaml --train --gpu 0 data.transform_fp=path_to_transform.json system.prompt_processor.prompt="text"
```
Find out more examples at `run.sh`.

## Citation

```bibtex
@article{wu2023ifusion,
  author = {Wu, Chin-Hsuan and Chen, Yen-Chun, Solarte, Bolivar and Yuan, Lu and Sun, Min},
  title = {iFusion: Inverting Diffusion for Pose-Free Reconstruction from Sparse Views},
  journal = {arXiv preprint arXiv:2312.17250},
  year = {2023}
}
```

## Acknowledgements
This code is built upon [threestudio](https://github.com/threestudio-project/threestudio). We sincerely thank all the contributors for their efforts!