"""Lossless packet boundaries for the installed HPL2 OTA first-byte bug.

This module does not open devices. Never insert, remove or alter image bytes.
"""


def next_end(image, start, maximum=55):
    if not 0 <= start < len(image) or not 1 <= maximum <= 55:
        raise ValueError('Invalid packet boundary')
    if image[start] >= 128:
        raise ValueError(f'Installed receiver would discard offset {start:#x}')
    end = min(len(image), start+maximum)
    if end == len(image):
        return end
    while end > start and image[end] >= 128:
        end -= 1
    if end == start:
        raise ValueError(f'No lossless compatible boundary after offset {start:#x}')
    return end


def plan(image, maximum=55):
    result=[]; offset=0
    while offset < len(image):
        end=next_end(image,offset,maximum)
        result.append((offset,end));offset=end
    assert b''.join(image[a:b] for a,b in result)==image
    return result
