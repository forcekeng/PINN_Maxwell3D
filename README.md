# 简介
使用PINN求解频域Maxwell3D问题。

# 内容
项目包含三个文件夹：
- `3D_dielectric_slab/` : 使用PINN仿真非均匀电介质，并使用部分外部测量数据。
- `3D_waveguide_cavity/` : 使用PINN仿真均匀介质，直接使用公式生成数据。
- `validation/` : Nvidia Modulus电磁场仿真中所有数据，已转换成 `.npy` 在`3D_dielectric_slab/` 中使用。

具体内容详见每个工程下的`README.md`介绍。

