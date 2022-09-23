import time
import math
import sys, os

import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


import PIL

from gimpformats.gimpXcfDocument import GimpDocument

class DocumentCache():
    def __init__(self):
        self.cache = {}

    def load_document(self, filename):
        try:
            return self.cache[filename]
        except KeyError:
            return GimpDocument(filename)

class CropBox():
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def box(self):
        return (self.x, self.y, self.x+self.w, self.y+self.h)

class Actor():

    def __init__(self, config, cache):
        self.uuid = config.get('name', 'Anonymous')

        self.doc = cache.load_document(config['file'])
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
    outdir = 'outputs'

    def __init__(self, config, cache):
        self.config = config

        self.doc = cache.load_document(config['file'])
        self.load_doc()

        self.first = config.get('first_frame', 0)
        self.length = config['length']
        self.split = config.get('split', 0)
        self.outname = config.get('output', 'out')
        if '.gif' in self.outname:
            self.outname = self.outname.replace('.gif','')

        self.crop = None
        if 'crop' in config.keys():
            self.crop = CropBox(**config['crop'])

        self.resize = config.get('resize', False)

        self.preview = config.get('preview', False)

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

        if self.crop:
            frame = frame.crop(box=self.crop.box())

        if self.resize:
            w,h = frame.size
            s = 800/w
            frame = frame.resize((int(w*s), int(h*s)))
 
        return frame

    def make_frames(self, actors):
        frames = [self.stamp_frame(x, actors) for x in range(self.length)]
        first = frames[self.first]
        last = frames[-1]
        frames = [*frames[self.split:], *frames[self.first:self.split]]
        return frames, first, last

    def outfile(self, suffix=''):
        return os.path.join(self.outdir, f'{self.outname}{suffix}.gif')

    def render(self, actors):

        frames, first, last = self.make_frames(actors)

        firstout = self.outfile('_first')
        first.save(firstout)
        lastout = self.outfile('_last')
        last.save(lastout)

        if self.preview:
            first.show()
            last.show()

        outname = self.outfile()
        frames[0].save(outname, save_all=True, append_images = frames[1:], duration=100, loop=0)


with open(sys.argv[1], 'r') as fp:
    config = yaml.load(fp, Loader=Loader)

doc_cache = DocumentCache()

print(f'Loading Scene')

scene = Scene(config['scene'], doc_cache)

print(f'Loading actors')
actors = []
for aconfig in config['actors']:
    actors.append(Actor(aconfig, doc_cache))

print(f'Rendering')

scene.render(actors)

#walking in place
#walking in place
#3-panel loop
#walk across 3 panels
#1-panel loop
#walk across extended 3 panels
#walk across extended 1 panel


