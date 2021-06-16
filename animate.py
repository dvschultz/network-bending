import argparse
import os
import subprocess
import torch
import yaml
import faulthandler
import numpy as np
import matplotlib.pyplot as plt

from torchvision import utils
from model import Generator
from tqdm import tqdm
from util import *

def animate_from_latent(args, g_ema, device, mean_latent, cluster_config, layer_channel_dims, latent):
    with torch.no_grad():
        g_ema.eval()
        increment = ( args.end_val - args.init_val ) / float(args.num_frames)
        
        for i in tqdm(range(args.num_frames)):
            param = args.init_val + (increment * (i+1))
            if args.transform == "rotate":
              param = (param % 360.0)
            print("animating frame: " +str(i) + " , param: " +str(param))
            if args.transform == "translate_x":
                transform = "translate"
                params = [param,0]
            elif args.transform == "translate_y":
                transform = "translate"
                params = [0,param]
            else:
                transform = args.transform
                params = [param]
            
            if args.cluster_id == -1:
                t_dict_list = [create_layer_wide_transform_dict(args.layer_id, layer_channel_dims, transform, params)]
            else:
                t_dict_list = [create_cluster_transform_dict(args.layer_id, layer_channel_dims, cluster_config, transform, params, args.cluster_id)]
            
            #pass in audio count
            if(args.audio_affects == "truncation"):
                # trnc = mapped(audio[os.path.basename(args.audio_file)[:-4]][i],0.0,1.0,0.1,1.0)
                # trnc = audio[os.path.basename(args.audio_file)[:-4]][i]
                trnc = 1-audio[os.path.basename(args.audio_file)[:-4]][i]
            else:
                trnc = args.truncation
                # trnc = i/args.num_frames

            if args.interpolate_ids != "":
                interp_frames = int(args.num_frames/(len(latents)-1))
                start_z = int(i/interp_frames)
                fraction = (i % interp_frames) / interp_frames
                counter = str(start_z)+'/'+str(len(latents))
                print(interp_frames, counter, fraction)

                # capture frame count overflow
                if(start_z >= (len(latents)-1)):
                    latent = latents[start_z]
                else :
                    latent = (latents[start_z+1]*fraction) + (latents[start_z]*(1-fraction))
                sample, _ = g_ema([latent],truncation=trnc, randomize_noise=False, truncation_latent=mean_latent, transform_dict_list=t_dict_list)
            else:
                sample, _ = g_ema([latent],truncation=trnc, randomize_noise=False, truncation_latent=mean_latent, transform_dict_list=t_dict_list)

            if not os.path.exists(args.dir):
                os.makedirs(args.dir)

            utils.save_image(
                sample,
                f'{str(args.dir)}/frame{str(i).zfill(6)}.png',
                nrow=1,
                normalize=True,
                range=(-1, 1),
            )

if __name__ == '__main__':
    device = 'cuda'

    parser = argparse.ArgumentParser()

    parser.add_argument('--size', type=int, default=1024)
    parser.add_argument('--sample', type=int, default=1)
    parser.add_argument('--pics', type=int, default=20)
    parser.add_argument('--truncation', type=float, default=0.5)
    parser.add_argument('--truncation_mean', type=int, default=4096)
    parser.add_argument('--ckpt', type=str, default="models/stylegan2-ffhq-config-f.pt")
    parser.add_argument('--channel_multiplier', type=int, default=2)
    parser.add_argument('--config', type=str, default="configs/example_transform_config.yaml")
    parser.add_argument('--clusters', type=str, default="configs/example_cluster_dict.yaml")
    parser.add_argument('--load_latent', type=str, default="")
    parser.add_argument('--audio_file', type=str, default="")
    parser.add_argument('--audio_affects', type=str, default="")
    parser.add_argument('--fps', type=int, default=24)
    parser.add_argument('--interpolate', type=int, default = 0)
    parser.add_argument('--interpolate_ids', type=str, default = "0,1")
    parser.add_argument('--latent_id', type=int, default= 0)
    parser.add_argument('--transform', type=str, default="")
    parser.add_argument('--init_val',type=float, default = 0)
    parser.add_argument('--end_val', type=float, default = 1)
    parser.add_argument('--num_frames', type=int, default = 100)
    parser.add_argument('--cluster_id', type=int, default = -1)
    parser.add_argument('--layer_id', type=int, default = 1)
    parser.add_argument('--dir', type=str, default="sample-animation")


    args = parser.parse_args()

    args.latent = 512
    args.n_mlp = 8

    if(args.audio_file != ""):
        audio = get_waveform(args.audio_file, args.fps)
        # print(audio)
        args.num_frames = len(audio[os.path.basename(args.audio_file)[:-4]])
        print('overriding num_frames, now: ', args.num_frames)

        # for track in sorted(audio.keys()):
        #     plt.figure(figsize=(8, 3))
        #     plt.title(track)
        #     plt.plot(audio[track])
        #     plt.savefig(f'../{track}.png')
    
    cluster_config = {}
    if args.clusters != "":
        with open(args.clusters, 'r') as stream:
            try:
                cluster_config = yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    latent_config = {}
    if args.load_latent != "":
        with open(args.load_latent, 'r') as stream:
            try:
                latent_config = yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)

    g_ema = Generator(
        args.size, args.latent, args.n_mlp, channel_multiplier=args.channel_multiplier
    ).to(device)
    new_state_dict = g_ema.state_dict()
    checkpoint = torch.load(args.ckpt)
    
    ext_state_dict  = torch.load(args.ckpt)['g_ema']
    g_ema.load_state_dict(checkpoint['g_ema'])
    new_state_dict.update(ext_state_dict)
    g_ema.load_state_dict(new_state_dict)
    g_ema.eval()
    g_ema.to(device)

    if args.truncation < 1:
        with torch.no_grad():
            mean_latent = g_ema.mean_latent(args.truncation_mean)
    else:
        mean_latent = None
    
    layer_channel_dims = create_layer_channel_dim_dict(args.channel_multiplier)


    # transform_dict_list = create_transforms_dict_list(yaml_config, cluster_config, layer_channel_dims)

    if args.load_latent == "":
        # generate(args, g_ema, device, mean_latent, yaml_config, cluster_config, layer_channel_dims)
        print("do nothing")
    elif args.interpolate_ids != "":
        # print(args.interpolate_ids)
        ls = args.interpolate_ids.split(',')
        latents=[]
        for l in np.arange(len(ls)):
          latents.append(torch.from_numpy(np.asarray(latent_config[int(ls[l])])).float().to(device))

        animate_from_latent(args, g_ema, device, mean_latent, cluster_config, layer_channel_dims, latents)
    else:
        latent = torch.from_numpy(np.asarray(latent_config[args.latent_id])).float().to(device)
        animate_from_latent(args, g_ema, device, mean_latent, cluster_config, layer_channel_dims, latent)

    cmd=f'ffmpeg  -r 24 -i {args.dir}/frame%06d.png -vcodec libx264 -pix_fmt yuv420p {args.dir}/bend.mp4 -y'

    #call ffmpeg command from python
    subprocess.call(cmd, shell=True)
    
    # config_out = {}
    # config_out['transforms'] = yaml_config['transforms']
    # with open(r'sample/config.yaml', 'w') as file:
    #     documents = yaml.dump(config_out, file)

