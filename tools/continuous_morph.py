"""Continuous bidirectional warp for existing drawings; no generated artwork."""
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image


@lru_cache(maxsize=32)
def fields(first: bytes, second: bytes) -> tuple[np.ndarray, np.ndarray]:
    a = np.frombuffer(first, np.uint8).reshape(512, 512)
    b = np.frombuffer(second, np.uint8).reshape(512, 512)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setFinestScale(0)
    dis.setGradientDescentIterations(40)
    dis.setVariationalRefinementIterations(10)
    return dis.calc(a, b, None), dis.calc(b, a, None)


ROLL_POINTS = [
    [(94,298),(150,370),(127,426),(207,405),(170,423),(52,326),(233,255),(60,462),(273,462),(327,292),(338,392),(134,463),(211,466),(332,457),(375,410),(412,453)],
    [(80,327),(140,375),(123,434),(185,408),(166,423),(57,378),(181,273),(65,477),(240,474),(325,314),(337,408),(147,463),(212,451),(348,471),(385,432),(417,451)],
    [(68,321),(125,364),(125,399),(174,374),(153,394),(50,375),(155,266),(60,464),(239,475),(321,306),(310,404),(218,396),(240,350),(322,424),(380,365),(425,445)],
    [(73,331),(129,366),(134,409),(181,380),(158,399),(55,387),(148,274),(62,472),(236,479),(309,319),(306,408),(219,396),(230,357),(330,420),(357,326),(433,449)],
    [(81,329),(130,373),(130,425),(170,395),(158,411),(50,389),(174,285),(62,480),(237,477),(298,311),(295,407),(215,397),(234,341),(350,365),(346,295),(421,451)],
    [(82,316),(129,352),(130,406),(168,377),(150,392),(51,373),(167,277),(63,475),(238,478),(296,322),(290,406),(211,384),(233,345),(337,406),(371,321),(419,452)],
    [(112,242),(158,304),(147,348),(199,322),(184,339),(47,351),(172,266),(62,470),(240,475),(294,332),(290,412),(198,365),(261,320),(278,393),(379,321),(426,452)],
]


def mesh_warp(pixels, source, target, triangles):
    x, y = np.meshgrid(np.arange(512, dtype=np.float32), np.arange(512, dtype=np.float32))
    u, v = x.copy(), y.copy()
    for indexes in triangles:
        destination = target[indexes]
        matrix = cv2.getAffineTransform(destination.astype(np.float32), source[indexes].astype(np.float32))
        mask = np.zeros((512,512), np.uint8)
        cv2.fillConvexPoly(mask, np.rint(destination).astype(np.int32), 1)
        inside = mask.astype(bool)
        u[inside] = matrix[0,0]*x[inside]+matrix[0,1]*y[inside]+matrix[0,2]
        v[inside] = matrix[1,0]*x[inside]+matrix[1,1]*y[inside]+matrix[1,2]
    return cv2.remap(pixels,u,v,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)


def morph(first: Image.Image, second: Image.Image, fraction: float, points=None) -> Image.Image:
    fraction = float(fraction)
    if fraction <= 0: return first.copy()
    if fraction >= 1: return second.copy()
    a, b = [np.asarray(im.convert("RGBA")).astype(np.float32) / 255 for im in (first, second)]
    for pixels in (a, b):
        pixels[..., :3] *= pixels[..., 3:4]
    if points is not None:
        boundary = [(0,0),(511,0),(511,511),(0,511),(256,0),(511,256),(256,511),(0,256)]
        pa, pb = [np.float32(p + boundary) for p in points]
        mean = (pa+pb)/2
        subdiv = cv2.Subdiv2D((0,0,512,512))
        for p in mean: subdiv.insert(tuple(map(float,p)))
        triangles=[]
        for tri in subdiv.getTriangleList().reshape(-1,3,2):
            indexes = [int(np.argmin(np.linalg.norm(mean-p,axis=1))) for p in tri]
            if all(np.linalg.norm(mean[i]-p)<1 for i,p in zip(indexes,tri)):
                triangles.append(indexes)
        target = pa*(1-fraction)+pb*fraction
        a,b = mesh_warp(a,pa,target,triangles),mesh_warp(b,pb,target,triangles)

    def gray(pixels):
        rgb = pixels[..., :3] + (1 - pixels[..., 3:4]) * 0.5
        return cv2.cvtColor(np.uint8(np.clip(rgb * 255, 0, 255)), cv2.COLOR_RGB2GRAY)

    forward, backward = fields(gray(a).tobytes(), gray(b).tobytes())
    if points is not None:
        forward = np.clip(forward, -3, 3)
        backward = np.clip(backward, -3, 3)
    x, y = np.meshgrid(np.arange(512, dtype=np.float32), np.arange(512, dtype=np.float32))

    def warp(pixels, flow, amount):
        # Solve inverse correspondence, rather than treating a forward field
        # as a backward field at the destination coordinate.
        u, v = x.copy(), y.copy()
        for _ in range(5):
            displacement = cv2.remap(flow, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            u = x - displacement[..., 0] * amount
            v = y - displacement[..., 1] * amount
        return cv2.remap(pixels, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    wa, wb = warp(a, forward, fraction), warp(b, backward, 1 - fraction)
    # Correspondence supplies the movement. A short, continuous texture handoff
    # preserves ink instead of leaving two half-transparent drawings for half
    # the action. Unlike an instantaneous source switch, it has no discontinuity.
    # Hand off corresponding regions successively rather than crossfading
    # every outline at once. The narrow feather stays local to the moving band.
    threshold = 0.34 + 0.32 * (1 - x / 511)
    transfer = np.clip((fraction - threshold + 0.04) / 0.08, 0, 1)[...,None]
    transfer = transfer * transfer * (3 - 2 * transfer)
    mixed = wa * (1 - transfer) + wb * transfer
    rgb = mixed[..., :3] / np.maximum(mixed[..., 3:4], 0.001)
    return Image.fromarray(np.uint8(np.clip(np.concatenate((rgb, mixed[..., 3:4]), axis=2) * 255, 0, 255)))
