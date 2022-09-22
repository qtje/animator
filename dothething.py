import time
import math

import PIL

from gimpformats.gimpXcfDocument import GimpDocument

class CropBox():
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

class Actor():
    xoff_base = -13#75
    yoff_base = 80

    walk_offsets = [
    0,
    9,
    20,
    30,
    43,
    57,
    73,
    ]

    def __init__(self, uuid):
        self.uuid = uuid

        self.doc = GimpDocument('walkcyclemasked.xcf')
        self.frames = {}
        self.masks = {}
    
        self.load_doc()
        self.make_masks(force=True)

        self.crop = None
        self.crop = CropBox(88,76,345,345)

        self.phase = 0
        self.trail = 7
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

    def get_offsets(self, idx, cidx):
        xoff = self.xoff_base+self.walk_offsets[idx]+cidx*self.walk_offsets[-1] - self.walk_offsets[self.phase]
        yoff = self.yoff_base

        return xoff, yoff

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
            print(e)
 
        return target
 
 
    def stamp_outline(self, gidx, target):

        base_gidx = gidx

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
            except ValueError as e:
                print(e)

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
    def __init__(self):
        self.doc = GimpDocument('page8_test.xcf')       
        self.load_doc()

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


scene = Scene()

#test = scene.stamp_frame(10, [actor])
#test.show()

actors = []

actor = Actor('walk1')
actors.append(actor)

actor = Actor('walk2')
actor.crop.x = 460
actor.xoff_base += 373
actor.phase=2
actors.append(actor)

actor = Actor('walk2')
actor.crop.x = 828
actor.xoff_base += 373*2
actor.phase=4
actors.append(actor)

frames = [scene.stamp_frame(x, actors) for x in range(40)]

frames[0].save('out.gif', save_all=True, append_images = frames[1:], duration=100, loop=0)


"""
def do_animation():

    ntop = output.nodeByName('top')
    nbot = layers.nodeByName('bottom')
    nbg = output.nodeByName('background')

    nframe = output.nodeByName('frames')
    bframe = output.nodeByName('bgframes')
    bmask = output.nodeByName('bgmask')

    nframe.enableAnimation()
    bframe.enableAnimation()
    bmask.enableAnimation()

    actor = Actor('walk1')

    actors = [actor]

    #TODO ensure unique uuid's for actors

    #TODO implement this
    for actor in actors:
        actor.generate_layers(output)

    output.setFramesPerSecond(10)

    kr.setActiveDocument(output)

#    for gidx in range(96):
    for gidx in range(10):

        output.setCurrentTime(gidx)
        output.setActiveNode(nframe)
        kr.action('add_blank_frame').trigger()
        output.setActiveNode(bframe)
        kr.action('add_blank_frame').trigger()
        output.setActiveNode(bmask)
        kr.action('add_blank_frame').trigger()

        #stamp top layer
        actor.stamp_frame(output, gidx, nframe)

        #stamp bottom layer
        actor.stamp_outline(output, gidx, nbot, bframe, bmask)
"""

