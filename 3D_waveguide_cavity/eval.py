import mindspore as ms
import mindspore.nn as nn
import mindspore.ops as ops
import mindspore.numpy as ms_np
from mindspore import ms_function
from mindspore import Tensor
from mindspore.train.serialization import load_checkpoint, load_param_into_net

from mindelec.architecture import MultiScaleFCCell
from mindelec.operators import SecondOrderGrad, Grad
from mindelec.common import PI

import os
import time
import tqdm
import numpy as np
import matplotlib.pyplot as plt

from src.config import maxwell_3d_config

def plot_waveguide(Ex_pred, Ey_pred, Ez_pred, Ez_true, Ez_diff, xyrange=(0,2),
                  save_dir=""):
    fig, axes =  plt.subplots(1, 3, figsize=(12, 3))
    ax0 = axes[0].imshow(Ez_pred, vmin=0, vmax=1.0, cmap='jet')
    axes[0].set_xticks([0, len(Ez_pred)], xyrange)
    axes[0].set_yticks([0, len(Ez_pred)], xyrange)
    axes[0].set_title("ground truth")
    
    ax1 = axes[1].imshow(Ez_true, vmin=0, vmax=1.0, cmap='jet')
    axes[1].set_xticks([0, len(Ez_pred)], xyrange)
    axes[1].set_yticks([0, len(Ez_true)], xyrange)
    axes[1].set_title("prediction")
    
    vmax = np.ceil(Ez_diff.max()*100)/100
    ax2 = axes[2].imshow(Ez_diff, vmin=0, vmax=vmax, cmap='binary')
    axes[2].set_xticks([0, len(Ez_pred)], xyrange)
    axes[2].set_yticks([0, len(Ez_diff)], xyrange)
    axes[2].set_title("difference")
    
    fig.colorbar(ax0, ax=[axes[0], axes[1]], shrink=0.8)
    fig.colorbar(ax2, ax=axes[2], shrink=0.8)
    
    plt.savefig(f"{save_dir}/waveguide_Ez.png", dpi=200,bbox_inches='tight')
    # plt.show()
    

    
def plot_domain_result(u1, u2, u3, xyrange, save_dir=""):
    vmax = np.max([u1, u2, u3])
    vmin = np.min([u1, u2, u3])
    fig, axes =  plt.subplots(4, 3, figsize=(10, 10))
    for e in range(3):
        ax = axes[0, e].imshow(u1[e], vmin=vmin, vmax=vmax, cmap='jet')
        axes[0, e].set_xticks([0, len(u1[e])], xyrange)
        axes[0, e].set_yticks([0, len(u1[e])], xyrange)
    for e in range(3):
        ax = axes[1, e].imshow(u2[e], vmin=vmin, vmax=vmax, cmap='jet')
        axes[1, e].set_xticks([0, len(u2[e])], xyrange)
        axes[1, e].set_yticks([0, len(u2[e])], xyrange)
    for e in range(3):
        ax = axes[2, e].imshow(u3[e], vmin=vmin, vmax=vmax, cmap='jet')
        axes[2, e].set_xticks([0, len(u3[e])], xyrange)
        axes[2, e].set_yticks([0, len(u3[e])], xyrange)
    fig.colorbar(ax, ax=[axes[e, xyz] for e in range(3)  for xyz in range(3)], shrink=0.6)
    
    for e in range(3):
        axes[3, e].set_xticks([])
        axes[3, e].set_yticks([])
        axes[3, e].spines['top'].set_visible(False)
        axes[3, e].spines['right'].set_visible(False)
        axes[3, e].spines['bottom'].set_visible(False)
        axes[3, e].spines['left'].set_visible(False)
    text = plt.text(x=-2,#??????x????????? 
         y=0.5, #??????y?????????
         s='Top to down is 3 planes: x=1, y=1, z=1\nLeft to right are 3 components: $E_x$, $E_y$, $E_z$', #????????????
         fontdict=dict(fontsize=12, color='r',family='monospace',),#??????????????????
         #?????????????????????
         bbox={'facecolor': '#74C476', #?????????
              'edgecolor':'b',#?????????
               'alpha': 0.5, #????????????
               'pad': 8,#???????????????????????? 
              }
        )
    text.set_color('b')#??????????????????
    
    plt.savefig(f"{save_dir}/domain_predict.png", dpi=200, bbox_inches='tight')
    # plt.show()

    
# ??????????????????
class TestMaxwell3DCavity():
    """???????????????????????????????????????L2????????????MSR??????"""
    def __init__(self, config):
        self.config = config
        
        self.net = self.init_net()
        
        self.concat = ops.Concat(1)
        self.abs = ops.Abs()
        
        self.zeros_like = ops.ZerosLike()
        self.wave_number = Tensor(self.config["wave_number"], ms.dtype.float32) # ??????
        self.pi = Tensor(PI, ms.dtype.float32) # ??????pi
        self.eigenmode = Tensor(self.config["eigenmode"], ms.dtype.float32) # ????????????
        
        # ???????????????
        self.xyrange = (self.config["coord_min"][0], self.config["coord_max"][0]) 
    
    def init_net(self):
        def load_paramters_into_net(param_path, net):
            """????????????????????????"""
            param_dict = load_checkpoint(param_path)
            convert_ckpt_dict = {}
            for _, param in net.parameters_and_names():
                convert_name1 = "jac2.model.model.cell_list." + param.name
                convert_name2 = "jac2.model.model.cell_list." + ".".join(param.name.split(".")[2:])
                for key in [convert_name1, convert_name2]:
                    if key in param_dict:
                        convert_ckpt_dict[param.name] = param_dict[key]
            load_param_into_net(net, convert_ckpt_dict)
            print("Load parameters finished!")
        
        net = MultiScaleFCCell(in_channel=self.config["in_channel"], 
                   out_channel=self.config["out_channel"], 
                   layers=self.config["layers"],
                   neurons=self.config["neurons"],
                  )
        load_paramters_into_net(self.config["param_path"],  net)
        return net
        

    def run(self):
        """?????????????????????????????????"""
        
        print("<===================== Begin evaluating =====================>")
        t_start = time.time()
        xmin, ymin, zmin = self.config["coord_min"]
        xmax, ymax, zmax = self.config["coord_max"]
        xyrange = (xmin, xmax)
        axis_size = self.config["axis_size"]
        save_dir = self.config["result_save_dir"]
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        if save_dir.endswith('/'):
            save_dir = save_dir[:-1]
    
        u = np.linspace(xmin, xmax, axis_size) # ?????????????????????????????????
        v = np.linspace(ymin, ymax, axis_size)
        U, V = np.meshgrid(u, v)
        uu, vv = U.reshape(-1,1), V.reshape(-1,1)
        ones = np.ones_like(uu)

        # ?????????4?????????
        plane0 = np.c_[ones*0, uu, vv] # x=0, yz, ???????????????????????????1??????????????????x,y,z?????????
        plane1 = np.c_[ones, uu, vv] # x=1, yz, 
        plane2 = np.c_[uu, ones, vv] # xz, y=1
        plane3 = np.c_[uu, vv, ones] # xy, z=1
        
        # ??????0??????????????????
        label0, E0, diff0 = self.get_waveguide_residual(plane0)
        shape = U.shape # ????????????
        Ex_pred = E0[:, 0].reshape(shape)
        Ey_pred = E0[:, 1].reshape(shape)
        Ez_pred = E0[:, 2].reshape(shape)
        Ez_true = label0[:, 2].reshape(shape)
        Ez_diff = diff0[:, 2].reshape(shape)
        
        print(f"Max difference of waveguide port in Ex: {diff0[:, 0].max():.5f}")
        print(f"Max difference of waveguide port in Ey: {diff0[:, 1].max():.5f}")
        print(f"Max difference of waveguide port in Ez: {diff0[:, 2].max():.5f}")
        plot_waveguide(Ex_pred, Ey_pred, Ez_pred, Ez_true, Ez_diff, xyrange, save_dir)
        print("plot waveguide completed!")
        
        # ??????1???2???3
        E1 = self.net(ms.Tensor(plane1, ms.dtype.float32)).asnumpy()  # x=0, yz??????
        E2 = self.net(ms.Tensor(plane2, ms.dtype.float32)).asnumpy()  # y=0, xz??????
        E3 = self.net(ms.Tensor(plane3, ms.dtype.float32)).asnumpy()  # z=0, xy??????
        
        # ????????????
        E1 = E1.reshape((U.shape[0], U.shape[1], 3)).transpose(2, 0, 1)
        E2 = E2.reshape((U.shape[0], U.shape[1], 3)).transpose(2, 0, 1)
        E3 = E3.reshape((U.shape[0], U.shape[1], 3)).transpose(2, 0, 1)
        plot_domain_result(E1, E2, E3, xyrange, save_dir)
        print("plot domain result completed!")
        
        # ??????????????????????????????
        print("Begin scan the whole volumn, it may take a long time.")
        # result[i, x, y, z]
        # i=0 -> Ex,  i=1 -> Ey, i=2 -> Ez
        # (x,y,z)??????????????????
        result = np.zeros(shape=(3, axis_size, axis_size, axis_size), dtype=np.float32)
        for i, x in tqdm.tqdm(enumerate(np.linspace(xmin, xmax, axis_size))):
            xx = ones * x
            points = ms.Tensor(np.c_[xx, uu, vv], ms.dtype.float32)
            u_xyz = self.net(points).asnumpy()
            result[0, i, :, :] = u_xyz[:, 0].reshape((axis_size, axis_size)).T
            result[1, i, :, :] = u_xyz[:, 1].reshape((axis_size, axis_size)).T
            result[2, i, :, :] = u_xyz[:, 2].reshape((axis_size, axis_size)).T
        np.save(f"{save_dir}/cavity_result.npy", result)
        
        print("<===================== End evaluating =====================>")
        t_end = time.time()
        print(f"This evaluation total spend {(t_end - t_start) / 60:.2f} minutes.")

        
    
    def get_waveguide_residual(self, data):
        """?????????????????????????????????????????????????????????????????????
         Args:
             data: shape=(n,3), n????????????3???????????????x,y,z??????
        
        Return:
            label: shape=(n,3), ?????????
            u: shape=(n,3), 3?????????????????????????????????Ex, Ey, Ez
            diff: shape=(n,3), ?????????label????????????u?????????
        """
        data = ms.Tensor(data, ms.dtype.float32)
        u = self.net(data)
        ## Ez = sin(m * pi * y / height) * sin(m * pi * y / length)
        height = self.config["coord_max"][1] # y????????????????????????y?????????
        length = self.config["coord_max"][2] # z????????????????????????z?????????
        # data[:,0]->x, data[:,1]->y, data[:,2]->z
        label_z = ops.sin(self.eigenmode * self.pi * data[:, 1:2] / height) * \
                        ops.sin(self.eigenmode * self.pi * data[:, 2:3] / length)
        label = self.concat((self.zeros_like(label_z), self.zeros_like(label_z), label_z))
        diff = self.abs(u - label)
        return label.asnumpy(), u.asnumpy(), diff.asnumpy()
    
if __name__ == "__main__":
    tester = TestMaxwell3DCavity(config=maxwell_3d_config)
    tester.run()
    
    """
    # ??????????????????????????????????????????????????? xxx.npy ?????????????????????Ex, Ey, Ez??????
    # result[i, x, y, z] ?????????i???????????????(x,y,z)??????
    # x,y,z???????????? [0, axis_size-1]????????? axis_size=101
    # i=0??????Ex, i=1??????Ey, i=2??????Ez
    # ????????????????????????????????????????????????????????????
    
    import numpy as np
    import matplotlib.pyplot as plt
    result = np.load('result/cavity_result.npy')
    plt.imshow(result[2, :, :, 51], cmap='jet')
    plt.colorbar()
    plt.show()
    """