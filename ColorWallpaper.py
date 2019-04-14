import re
import argparse

from pathlib import Path
from PIL import Image, ImageDraw
from typing import Tuple, Union, List
from colorsys import rgb_to_hsv, rgb_to_hls

from data import *


__all__ = ['Wallpaper']

hex_re = re.compile(r'\s*#?([\da-f]{6}|[\da-f]{3})\s*', re.I)
rgb_re = re.compile(r'\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\s*')
resolution_re = re.compile(r'\s*(\d+)\s*[x:]\s*(\d+)\s*')


def get_options(args=None) -> argparse.Namespace:
    def normalized(s: str) -> str:
        return ''.join(s.split()).lower()

    def int_tuple(*t) -> Tuple[int, ...]:
        return tuple(map(int, t))

    def parse_hex(arg: str) -> Tuple[int, int, int]:
        le = len(arg)
        return tuple(int(arg[le//3*i:le//3*(i+1)], 16) for i in range(3))

    def color(arg: str) -> Color:
        hex_groups = hex_re.fullmatch(arg)
        rgb_groups = rgb_re.fullmatch(arg)

        name = None

        if hex_groups is not None:
            rgb = parse_hex(hex_groups.group(1))
        elif rgb_groups is not None:
            rgb = int_tuple(rgb_groups.group(0),
                            rgb_groups.group(1),
                            rgb_groups.group(2))
            if not all(0 <= c <= 255 for c in rgb):
                raise argparse.ArgumentTypeError('invalid RGB values')
        else:
            name = normalized(arg)
            if name not in color_to_hex:
                raise argparse.ArgumentTypeError(f'{arg} is not a color')

            rgb = parse_hex(color_to_hex[name])

        if name is None:
            name = 'anonymous'

        return Color(rgb, pretty_names.get(name, name.capitalize()))

    def inverted_color(source: Tuple[int, int, int]) -> Color:
        rgb: Tuple[int, int, int] = tuple(255 - x for x in source)
        return Color(rgb, hex_to_color.get(''.join(f'{c:02x}' for c in rgb)))

    def resolution(arg: str) -> Tuple[int, int]:
        groups = resolution_re.fullmatch(arg)

        if groups is None:
            raise argparse.ArgumentTypeError('Unable to parse the resolution')

        res = int_tuple(groups.group(1), groups.group(2))

        if any(dimension < 150 for dimension in res):
            raise argparse.ArgumentTypeError('Minimal resolution is 150x150')

        return res

    ret = argparse.ArgumentParser(description='Minimalist wallpaper generator')

    ret.add_argument('-o', '--output', metavar='PATH', default=Path('out.png'),
                     type=Path, help='Image output path')

    ret.add_argument('-c', '--color', default=Color((255, 2, 141), 'Hot Pink'),
                     type=color, help='#Hex / R,G,B / name of background color')

    ret.add_argument('-c2', '--color2', metavar='COLOR',
                     type=color, help='#Hex / R,G,B / name of highlight color')

    ret.add_argument('-r', '--resolution', default=(1920, 1080),
                     type=resolution, help='WIDTHxHEIGHT')

    ret.add_argument('-f', '--formats', default=['empty', 'hex', 'rgb'],
                     help='Declares the order and formats to display',
                     type=normalized, nargs='+',
                     choices=['empty', 'hex', '#hex', 'rgb', 'hsv', 'hsl',
                              'cmyk'])

    ret.add_argument('-l', '--lowercase', action='store_true',
                     help='Casing of hex output')

    ret.add_argument('-y', '--yes', action='store_true',
                     help='Force overwrite of --output')

    ret = ret.parse_args(args)

    if ret.color2 is None:
        ret.color2 = inverted_color(ret.color.rgb)

    return ret


class Color:
    def __init__(self, rgb: Tuple[int, int, int], name: str):
        self.rgb = rgb
        self.name = name

    @property
    def hsv(self) -> Tuple[int, int, int]:
        h, s, v = rgb_to_hsv(*(comp/255 for comp in self.rgb))

        return int(h*360), int(s*100), int(v*100)

    @property
    def hsl(self) -> Tuple[int, int, int]:
        h, l, s = rgb_to_hls(*(comp/255 for comp in self.rgb))

        return int(h*360), int(s*100), int(l*100)

    @property
    def cmyk(self) -> Tuple[int, int, int, int]:
        c, m, y = (1 - comp/255 for comp in self.rgb)

        k = min(c, m, y, 1)

        if k == 1:
            return 0, 0, 0, 100

        c = (c - k) / (1.0 - k)
        m = (m - k) / (1.0 - k)
        y = (y - k) / (1.0 - k)

        return tuple(int(comp*100) for comp in (c, m, y, k))


class Wallpaper:
    def __init__(self, options: argparse.Namespace):
        self.output: Union[str, Path] = options.output
        self.resolution: Tuple[int, int] = options.resolution
        self.color: Color = options.color
        self.color2: Color = options.color2
        self.formats: List[str] = options.formats
        self.x: str = 'x' if options.lowercase else 'X'
        self.y: bool = options.yes

    def __generate_text(self, text: str) -> Image.Image:
        text_length = sum(len(font(char)[0]) for char in text) - 1
        img = Image.new('RGBA', (text_length, 8), (0, 0, 0, 0))
        offset = 0
        x = 0

        for char in text:
            pixel_map = font(char)

            for y in range(len(pixel_map)):
                for x in range(len(pixel_map[y])):
                    if pixel_map[y][x]:
                        img.putpixel((offset + x, y), self.color2.rgb)

            offset += x + 1

        return img

    def __generate_decoration(self) -> Image.Image:
        img = Image.new('RGBA', (128, 128), (0, 0, 0, 0))

        ImageDraw.Draw(img).rectangle((0, 0, 127, 127),
                                      outline=self.color2.rgb, width=3)

        name = self.__generate_text(self.color.name)
        x, y = name.size

        if x <= 112:
            img.alpha_composite(name, (8, y))
        else:
            text1, text2 = self.color.name.rsplit(' ', 1)
            img.alpha_composite(self.__generate_text(text1), (8, y))
            y += 12
            img.alpha_composite(self.__generate_text(text2), (8, y))

        hex_format = f'{{0:02{self.x}}}'

        rows = {
            'hex': (
                'HEX ',
                ''.join(hex_format.format(c) for c in self.color.rgb)
            ),
            '#hex': (
                'HEX ',
                '#' + ''.join(hex_format.format(c) for c in self.color.rgb)
            ),
            'rgb': ('RGB ', ' '.join(map(str, self.color.rgb))),
            'hsv': ('HSV ', ' '.join(map(str, self.color.hsv))),
            'hsl': ('HSL ', ' '.join(map(str, self.color.hsl))),
            'cmyk': ('CMYK ', ' '.join(map(str, self.color.cmyk))),
            'empty': (' ', ' ')
        }

        for key in self.formats:
            y += 12
            label = self.__generate_text(rows[key][0])
            img.alpha_composite(label, (8, y))
            img.alpha_composite(self.__generate_text(rows[key][1]),
                                (3 + 5 + label.size[0], y))

        return img

    def generate_image(self) -> Image:
        img = Image.new('RGBA', self.resolution, self.color.rgb)

        smaller = min(self.resolution)
        decor_size = 128 * max(round(smaller / 4 / 128), 1)

        decoration = self.__generate_decoration()
        decoration = decoration.resize((decor_size, decor_size))

        img.alpha_composite(decoration, ((self.resolution[0]-decor_size) // 2,
                                         (self.resolution[1]-decor_size) // 2))

        if not self.output.exists():
            self.output.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(self.output))
        elif self.output.is_file():
            if self.y or input(f'File "{self.output}" exists.\n'
                               f'Overwrite? [y/n] ').lower().startswith('y'):
                img.save(str(self.output))
        else:
            raise IOError(f'The "{self.output}" exists and is not a file')


if __name__ == '__main__':
    Wallpaper(get_options()).generate_image()
