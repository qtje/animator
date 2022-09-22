import time
import math
import sys

import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


import PIL

from gimpformats.gimpXcfDocument import GimpDocument

class CropBox():
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

class Actor():

    def __init__(self, config):
        self.uuid = config.get('name', 'Anonymous')

        self.doc = GimpDocument('walkcyclemasked.xcf')
        self.frames = {}
        self.masks = {}
    
        self.load_doc()
        self.make_masks(force=True)

        self.crop = None
        if 'crop' in config.keys():
            self.crop = CropBox(**config['crop'])

        self.xoff_base = config['xoff']
        self.yoff_base = config['yoff']

        self.frame_xoffsets = config.get('frame_xoffsets', [0]*len(self.frames))
        self.frame_yoffsets = config.get('frame_yoffsets', [0]*len(self.frames))

        self.xspeed = config.get('xspeed', 1)
        self.yspeed = config.get('yspeed', 1)

        self.phase = config.get('phase', 0)
        self.trail = config.get('trail', 1)
        self.decay = 0.5


    def load_doc(self):
        def get_frame_number(frame):
            name = frame.name
            if not 'frame' in name: raise ValueError('Not a frame')
            return int(name[len('frame'):])
        def get_mask_number(frame):
            name = frame.name
            if not 'mask' in name: raise ValueError('Not a mask')
            return int(name[len('mask'):])

        for layer in self.doc.layers:
            try:
                index = get_frame_number(layer)
                self.frames[index] = layer.image
                continue
            except ValueError: pass
            try:
                index = get_mask_number(layer)
                self.masks[index] = layer.image
                continue
            except ValueError: pass

        self.frame_count = len(self.frames.keys())

    def decode_gidx(self, gidx):
        gidx += self.phase
        idx = gidx % self.frame_count
        cidx = int(math.floor(gidx/self.frame_count))

        return idx, cidx

    def get_displacement(self, offsets, idx, cidx):
        return offsets[idx] + cidx*offsets[-1] - offsets[self.phase]

    def get_offsets(self, idx, cidx):
        xdisp = self.get_displacement(self.frame_xoffsets, idx, cidx)
        xoff = self.xoff_base + xdisp*self.xspeed
       
        ydisp = self.get_displacement(self.frame_yoffsets, idx, cidx) 
        yoff = self.yoff_base + ydisp*self.yspeed

        return int(xoff), int(yoff)

    def get_boxes(self, xoff, yoff, w, h):
        crop = self.crop
        if crop is not None:
            left = max(xoff, crop.x)
            right = min(xoff+w, crop.x+crop.w)
            top = max(yoff, crop.y)
            bot = min(yoff+h, crop.y+crop.h)
            dest = (left, top)
            source = (left-xoff, top-yoff, right-xoff, bot-yoff)
        else:
            dest = (xoff, yoff)
            source = (0,0)

        return dest, source


    def stamp_frame(self, gidx, target):

        idx, cidx = self.decode_gidx(gidx)

        frame = self.frames[idx]

        xoff, yoff = self.get_offsets(idx, cidx)
        w,h = frame.size

        dest, source = self.get_boxes(xoff, yoff, w, h)
        try:
            target.alpha_composite(frame, dest=dest, source=source)
        except ValueError as e:
            pass
 
        return target
 
 
    def stamp_outline(self, gidx, target):

        base_gidx = gidx
        out_of_bounds = True

        for oidx in list(range(self.trail))[::-1]:
            gidx = base_gidx - oidx

            idx, cidx = self.decode_gidx(gidx)

            xoff, yoff = self.get_offsets(idx, cidx)

            mask = self.masks[idx]
            w,h = mask.size

            dest, source = self.get_boxes(xoff, yoff, w, h)

            empty = PIL.Image.new('RGBA', mask.size, (0,0,0,0))
            balpha = 0.5**(oidx*self.decay)
            mask_eff = PIL.Image.blend(empty, mask, balpha)

            try:
                target.alpha_composite(mask_eff, dest=dest, source=source)
                out_of_bounds = False
            except ValueError as e:
                pass

        if out_of_bounds:
            print(f'{self.uuid} out of bounds on {base_gidx}')

        return target

    def make_masks(self, force = False):

        for idx, frame in self.frames.items():
            if idx in self.masks.keys():
                mask = self.masks[idx]
                if not force: 
                    continue
            else:
                pass

class Scene():
    def __init__(self, config):
        self.config = config

        self.doc = GimpDocument(config['file'])
        self.load_doc()

        self.length = config['length']
        self.split = config.get('split', 0)

    def load_doc(self):
        for layer in self.doc.layers:
            name = layer.name.lower()
            image = layer.image
            if name == 'top':
                self.top = image
            elif name == 'bottom':
                self.bot = image
            elif name == 'background':
                self.bg = image

    def stamp_frame(self, idx, actors):
        frame = self.bg.copy()

        width, height = frame.size
        
        mask = PIL.Image.new('RGBA', frame.size, (0,0,0,0))

        for actor in actors:
            actor.stamp_outline(idx, mask)

        frame.paste(self.bot, mask=mask)

        for actor in actors:
            actor.stamp_frame(idx, frame)

        frame.alpha_composite(self.top)
 
        return frame

    def make_frames(self, actors):
        frames = [self.stamp_frame(x, actors) for x in range(self.length)]
        frames = [*frames[self.split:], *frames[:self.split]]
        return frames

with open(sys.argv[1], 'r') as fp:
    config = yaml.load(fp, Loader=Loader)

scene = Scene(config['scene'])

actors = []

for aconfig in config['actors']:
    actors.append(Actor(aconfig))

frames = scene.make_frames(actors)

frames[0].save('out.gif', save_all=True, append_images = frames[1:], duration=100, loop=0)

#walking in place
#walking in place
#3-panel loop
#walk across 3 panels
#1-panel loop
#walk across extended 3 panels
#walk across extended 1 panel


