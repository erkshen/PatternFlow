# -*- coding: utf-8 -*-
"""Stylegan_rosinality

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1z2Vt8eaB3pyMR9xx6spcpFYFaCk1XLdz
"""

from google.colab import drive
drive.mount('/content/drive')

#!git clone https://github.com/rosinality/style-based-gan-pytorch.git  /content/drive/MyDrive/StyleGAN_rosin

#cd /content/drive/MyDrive/StyleGAN_rosin

#!python prepare_data.py --out /content/drive/MyDrive/StyleGAN_rosin/LMDB_PATH --n_worker 2 /content/drive/MyDrive/Dataset_brain/keras_png_slices_data/

#!python train.py --mixing /content/drive/MyDrive/StyleGAN_rosin/LMDB_PATH

"""Test"""

#!python train.py --ckpt /content/drive/MyDrive/StyleGAN_rosin/checkpoint/train_step-4.model --mixing /content/drive/MyDrive/StyleGAN_rosin/LMDB_PATH

import os

#os.chdir('/content/drive/MyDrive/Stylegan_shang')   #修改当前工作目录

#!python train_SG.py --mixing /content/drive/MyDrive/StyleGAN_rosin/LMDB_PATH

import argparse
import random
import math

from tqdm import tqdm
import numpy as np
from PIL import Image

import torch
from torch import nn, optim
from torch.nn import functional as F
from torch.autograd import Variable, grad
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, utils

from Dataset import MultiResolutionDataset
from Model2 import StyledGenerator, Discriminator
import matplotlib.pyplot as plt

# use idel gpu
# it's better to use enviroment variable
# if using multiple gpus, please
# modify hyperparameters at the same time
# And Make Sure Your Pytorch Version >= 1.0.1
import os
os.environ['CUDA_VISIBLE_DEVICES']='0'
n_gpu             = 1
device            = torch.device('cuda:0')
Path='/content/drive/MyDrive/StyleGAN_rosin/LMDB_PATH'
ckpt=None




#learning_rate     = {128: 0.0015, 256: 0.002, 512: 0.003, 1024: 0.003}
batch_size_1gpu   = {4: 128, 8: 128, 16: 64, 32: 32, 64: 16, 128: 16}
mini_batch_size_1 = 8
#batch_size        = {4: 256, 8: 256, 16: 128, 32: 64, 64: 32, 128: 16}
mini_batch_size   = 8
batch_size_4gpus  = {4: 512, 8: 256, 16: 128, 32: 64, 64: 32}
mini_batch_size_4 = 16
batch_size_8gpus  = {4: 512, 8: 256, 16: 128, 32: 64}
mini_batch_size_8 = 32
n_fc              = 8
dim_latent        = 512
dim_input         = 4
n_sample          = 120000     #number of samples used for each training phases
DGR               = 1
n_show_loss       = 500
step              = 1 # Train from (8 * 8)
max_step          = 8 # Maximum step (8 for 1024^2)
#style_mixing      = [] # Waiting to implement
image_folder_path = '/content/drive/MyDrive/Dataset_brain/keras_png_slices_data'
save_folder_path  = '/content/drive/MyDrive/Stylegan_shang/results'

low_steps         = [0, 1, 2]
# style_mixing    += low_steps
mid_steps         = [3, 4, 5]
# style_mixing    += mid_steps
hig_steps         = [6, 7, 8]
# style_mixing    += hig_steps

# Used to continue training from last checkpoint
startpoint        = 0
used_sample       = 0
alpha             = 0

# Mode: Evaluate? Train?
is_train          = True

# How to start training?
# True for start from saved model
# False for retrain from the very beginning
is_continue       = True
d_losses          = [float('inf')]
g_losses          = [float('inf')]
inputs, outputs = [], []

def set_grad_flag(module, flag=True):
    for p in module.parameters():
        p.requires_grad = flag

def reset_LR(optimizer, lr):
    for pam_group in optimizer.param_groups:
        mul = pam_group.get('mul', 1)
        pam_group['lr'] = lr * mul


def accumulate(model1, model2, decay=0.999):
    par1 = dict(model1.named_parameters())
    par2 = dict(model2.named_parameters())

    for k in par1.keys():
        par1[k].data.mul_(decay).add_(1 - decay, par2[k].data)

        
# Gain sample
def gain_sample(dataset, batch_size, image_size=4):
    dataset.resolution = image_size
    loader = DataLoader(dataset, shuffle=True, batch_size=batch_size, num_workers=1, drop_last=True)

    return loader

def imshow(tensor, i):
    grid = tensor[0]
    grid.clamp_(-1, 1).add_(1).div_(2)
    # Add 0.5 after unnormalizing to [0, 255] to round to nearest integer
    ndarr = grid.mul_(255).add_(0.5).clamp_(0, 255).permute(1, 2, 0).to('cpu', torch.uint8).numpy()
    img = Image.fromarray(ndarr)
    #img.save(f'{save_folder_path}sample-iter{i}.png')
    plt.imshow(img)
    plt.show()

init_size=8 #Initial image size,default=8
batch_default=32
max_size=1024  #Max image size,default=1024
ckpt=None
loss='wgan-gp'  #options:wgan-gp,r1
#gen_sample = {512: (8, 4), 1024: (4, 2)}
mixing=True
no_from_rgb_activate=True
n_critic=1

#learning_rate.get(8,0.001)

def train(dataset, generator, discriminator,loss):
    step = int(math.log2(init_size)) - 2

    resolution = 4 * 2 ** step
    loader = gain_sample(
        dataset, batch_size.get(resolution, batch_default), resolution
    )
    data_loader = iter(loader)

    reset_LR(g_optimizer, learning_rate.get(resolution, 0.001))
    reset_LR(d_optimizer, learning_rate.get(resolution, 0.001))

    #Epoch=1,000,000

    #pbar = tqdm(range(1000000))
    pbar = tqdm(range(startpoint + 1, n_sample * 5))

    set_grad_flag(generator, False)
    set_grad_flag(discriminator, True)

    #Initializing
    disc_loss_val = 0
    gen_loss_val = 0
    grad_loss_val = 0

    alpha = 0
    used_sample = 0

    max_step = int(math.log2(max_size)) - 2
    final_progress = False

    for i in pbar:
        discriminator.zero_grad()

        #alpha = min(1, 1 / n_sample * (used_sample + 1))
        alpha = min(1, alpha + batch_size.get(resolution, mini_batch_size) / (n_sample * 2))

        if (resolution == init_size and ckpt is None) or final_progress:
            alpha = 1

        if used_sample > n_sample * 2:
            used_sample = 0
            step += 1

            if step > max_step:
                step = max_step
                final_progress = True
                ckpt_step = step + 1

            else:
                alpha = 0
                ckpt_step = step

            resolution = 4 * 2 ** step

            loader = gain_sample(
                dataset, batch_size.get(resolution, batch_default), resolution
            )
            data_loader = iter(loader)
            

            torch.save(
                {
                    'generator': generator.module.state_dict(),
                    'discriminator': discriminator.module.state_dict(),
                    'g_optimizer': g_optimizer.state_dict(),
                    'd_optimizer': d_optimizer.state_dict(),
                    'g_running': g_running.state_dict(),
                },
                f'checkpoint/train_step-{ckpt_step}.pth',
            )

            reset_LR(g_optimizer, learning_rate.get(resolution, 0.001))
            reset_LR(d_optimizer, learning_rate.get(resolution, 0.001))

        try:
            real_image = next(data_loader)

        except (OSError, StopIteration):
            data_loader = iter(loader)
            real_image = next(data_loader)

        used_sample += real_image.shape[0]

        b_size = real_image.size(0)
        real_image = real_image.cuda()

        #Loss function of discriminator
        if loss == 'wgan-gp':
            real_predict = discriminator(real_image, step=step, alpha=alpha)
            real_predict = real_predict.mean() - 0.001 * (real_predict ** 2).mean()
            (-real_predict).backward()

        elif loss == 'r1':
            real_image.requires_grad= True
            real_scores = discriminator(real_image, step=step, alpha=alpha)
            real_predict = F.softplus(-real_scores).mean()
            real_predict.backward(retain_graph=True)

            grad_real = grad(
                outputs=real_scores.sum(), inputs=real_image, create_graph=True
            )[0]
            grad_penalty = (
                grad_real.view(grad_real.size(0), -1).norm(2, dim=1) ** 2
            ).mean()
            grad_penalty = 10 / 2 * grad_penalty
            grad_penalty.backward()
            if i%10 == 0:
                grad_loss_val = grad_penalty.item()

        if mixing==True and random.random() < 0.9:
            gen_in11, gen_in12, gen_in21, gen_in22 = torch.randn(
                4, b_size, dim_latent, device='cuda'
            ).chunk(4, 0)
            gen_in1 = [gen_in11.squeeze(0), gen_in12.squeeze(0)]
            gen_in2 = [gen_in21.squeeze(0), gen_in22.squeeze(0)]

        else:
            gen_in1, gen_in2 = torch.randn(2, b_size, dim_latent, device='cuda').chunk(
                2, 0
            )
            gen_in1 = gen_in1.squeeze(0)
            gen_in2 = gen_in2.squeeze(0)

        fake_image = generator(gen_in1, step=step, alpha=alpha)
        fake_predict = discriminator(fake_image, step=step, alpha=alpha)

        if loss == 'wgan-gp':
            fake_predict = fake_predict.mean()
            fake_predict.backward()

            eps = torch.rand(b_size, 1, 1, 1).cuda()
            x_hat = eps * real_image.data + (1 - eps) * fake_image.data
            x_hat.requires_grad= True
            hat_predict = discriminator(x_hat, step=step, alpha=alpha)
            grad_x_hat = grad(
                outputs=hat_predict.sum(), inputs=x_hat, create_graph=True
            )[0]
            grad_penalty = (
                (grad_x_hat.view(grad_x_hat.size(0), -1).norm(2, dim=1) - 1) ** 2
            ).mean()
            grad_penalty = 10 * grad_penalty
            grad_penalty.backward()
            if i%10 == 0:
                grad_loss_val = grad_penalty.item()
                disc_loss_val = (-real_predict + fake_predict).item()

        elif loss == 'r1':
            fake_predict = F.softplus(fake_predict).mean()
            fake_predict.backward()
            if i%10 == 0:
                disc_loss_val = (real_predict + fake_predict).item()

        d_optimizer.step()

        #Loss function of generator
        if (i + 1) % n_critic == 0:
            generator.zero_grad()

            set_grad_flag(generator, True)
            set_grad_flag(discriminator, False)

            fake_image = generator(gen_in2, step=step, alpha=alpha)

            predict = discriminator(fake_image, step=step, alpha=alpha)

            if loss == 'wgan-gp':
                loss = -predict.mean()

            elif loss == 'r1':
                loss = F.softplus(-predict).mean()

            if i%10 == 0:
                gen_loss_val = loss.item()

            loss.backward(retain_graph=True)
            g_optimizer.step()
            accumulate(g_running, generator.module)

            set_grad_flag(generator, False)
            set_grad_flag(discriminator, True)

        if (i + 1) % 100 == 0:
            images = []

            gen_i, gen_j = gen_sample.get(resolution, (10, 5))

            with torch.no_grad():
                for _ in range(gen_i):
                    images.append(
                        g_running(
                            torch.randn(gen_j, dim_latent).cuda(), step=step, alpha=alpha
                        ).data.cpu()
                    )

            utils.save_image(
                torch.cat(images, 0),
                f'sample/{str(i + 1).zfill(6)}.png',
                nrow=gen_i,
                normalize=True,
                range=(-1, 1),
            )
            imshow(torch.cat(images, 0), i)

        if (i + 1) % 10000 == 0:
            torch.save(
                g_running.state_dict(), f'checkpoint/{str(i + 1).zfill(6)}.pth'
            )

        state_msg = (
            f'Size: {4 * 2 ** step}; G: {gen_loss_val:.3f}; D: {disc_loss_val:.3f};'
            f' Grad: {grad_loss_val:.3f}; Alpha: {alpha:.5f}'
        )

        pbar.set_description(state_msg)

no_from_rgb_activate=True

if __name__ == '__main__':

  generator = nn.DataParallel(StyledGenerator(dim_latent)).cuda()
  discriminator = nn.DataParallel(
        Discriminator(from_rgb_activate=not no_from_rgb_activate)
    ).cuda()

  g_running = StyledGenerator(dim_latent).cuda()
  g_running.train(False)

  g_optimizer = optim.Adam(
        generator.module.generator.parameters(), lr=0.001, betas=(0.0, 0.99)
    )
  
  g_optimizer.add_param_group(
        {
            'params': generator.module.style.parameters(),
            'lr': 0.001 * 0.01,
            'mult': 0.01,
        }
    )
  
  d_optimizer = optim.Adam(discriminator.parameters(), lr=0.001, betas=(0.0, 0.99))
  accumulate(g_running, generator.module, 0)


#Load pre-trained models
  if ckpt is not None:
        ckpt = torch.load(ckpt)

        generator.module.load_state_dict(ckpt['generator'])
        discriminator.module.load_state_dict(ckpt['discriminator'])
        g_running.load_state_dict(ckpt['g_running'])
        g_optimizer.load_state_dict(ckpt['g_optimizer'])
        d_optimizer.load_state_dict(ckpt['d_optimizer'])

  transform = transforms.Compose(
        [
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5), inplace=True),
        ]
    )

  dataset = MultiResolutionDataset(Path, transform)


  learning_rate = {128: 0.0015, 256: 0.002, 512: 0.003, 1024: 0.003}
  batch_size        = {4: 256, 8: 256, 16: 128, 32: 64, 64: 32, 128: 16}


  gen_sample = {512: (8, 4), 1024: (4, 2)}

  batch_default = 32

  loss='wgan-gp'

  train(dataset, generator, discriminator,loss)