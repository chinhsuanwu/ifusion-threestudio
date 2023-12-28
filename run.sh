root_dir="path/to/ifusion"

# Zero123
python launch.py --config configs/zero123.yaml --train --gpu 0 data.image_path=$root_dir/asset/sorter/0.png
python launch.py --config configs/zero123.yaml --train --gpu 0 data.image_path=$root_dir/asset/cat/0.png data.default_elevation_deg=10
python launch.py --config configs/zero123.yaml --train --gpu 0 data.image_path=$root_dir/asset/chair/0.png data.default_elevation_deg=10
python launch.py --config configs/zero123.yaml --train --gpu 0 data.image_path=$root_dir/asset/human-toy/0.png data.default_elevation_deg=10

# Zero123 + iFusion
python launch.py --config configs/zero123-ifusion.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/sorter/transform.json
python launch.py --config configs/zero123-ifusion.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/cat/transform.json data.default_elevation_deg=10
python launch.py --config configs/zero123-ifusion.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/chair/transform.json data.default_elevation_deg=10
python launch.py --config configs/zero123-ifusion.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/human-toy/transform.json data.default_elevation_deg=10

# Magic123
python launch.py --config configs/magic123-coarse-sd.yaml --train --gpu 0 data.image_path=$root_dir/asset/sorter/0.png
python launch.py --config configs/magic123-coarse-sd.yaml --train --gpu 0 data.image_path=$root_dir/asset/cat/0.png system.prompt_processor.prompt="a cat statue" data.default_elevation_deg=10
python launch.py --config configs/magic123-coarse-sd.yaml --train --gpu 0 data.image_path=$root_dir/asset/chair/0.png system.prompt_processor.prompt="a chair" data.default_elevation_deg=10
python launch.py --config configs/magic123-coarse-sd.yaml --train --gpu 0 data.image_path=$root_dir/asset/human-toy/0.png system.prompt_processor.prompt="a human toy" data.default_elevation_deg=10

# Magic123 + iFusion (recommended)
python launch.py --config configs/magic123-ifusion-coarse-sd.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/sorter/transform.json system.prompt_processor.prompt="a sorter"
python launch.py --config configs/magic123-ifusion-coarse-sd.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/cat/transform.json system.prompt_processor.prompt="a cat statue" data.default_elevation_deg=10
python launch.py --config configs/magic123-ifusion-coarse-sd.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/chair/transform.json system.prompt_processor.prompt="a chair" data.default_elevation_deg=10
python launch.py --config configs/magic123-ifusion-coarse-sd.yaml --train --gpu 0 data.transform_fp=$root_dir/asset/human-toy/transform.json system.prompt_processor.prompt="a human toy" data.default_elevation_deg=10