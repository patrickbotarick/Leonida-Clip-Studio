"""XML xmeml/FCP7 de origem única, CFR, em quadros absolutos zero/NDF."""
import copy
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from .exports import frame_rate


def element(parent, name, value=None, **attributes):
    node = ET.SubElement(parent, name, attributes)
    if value is not None:
        node.text = re.sub('[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]', '\ufffd', str(value))
    return node


def rate(parent, nominal, ntsc):
    node = element(parent, 'rate')
    element(node, 'timebase', nominal); element(node, 'ntsc', str(ntsc).upper())


def build_xml(project, plan):
    meta = project['metadata']
    fps, nominal, ntsc = frame_rate(meta)
    media_duration = math.ceil(meta['duration'] * fps)
    root = ET.Element('xmeml', version='5')
    seq = element(root, 'sequence', id='leonida-sequence')
    element(seq, 'name', project['name'] + (' · consolidada' if plan['sequence_mode'] == 'compact' else ' · posições originais'))
    element(seq, 'duration', plan['rows'][-1]['timeline_out'])
    rate(seq, nominal, ntsc)
    tc = element(seq, 'timecode'); rate(tc, nominal, ntsc)
    element(tc, 'string', '00:00:00:00'); element(tc, 'frame', 0); element(tc, 'displayformat', 'NDF')
    media = element(seq, 'media'); video = element(media, 'video')
    sample = element(element(video, 'format'), 'samplecharacteristics')
    rate(sample, nominal, ntsc)
    element(sample, 'width', meta['width']); element(sample, 'height', meta['height'])
    element(sample, 'anamorphic', 'FALSE'); element(sample, 'pixelaspectratio', 'square'); element(sample, 'fielddominance', 'none')
    video_track = element(video, 'track')
    audio = element(media, 'audio')
    audio_format = element(element(audio, 'format'), 'samplecharacteristics')
    element(audio_format, 'depth', 16); element(audio_format, 'samplerate', 48000)
    # FCP7 sourcetrack conta os canais da mídia em ordem, não o índice global FFmpeg.
    channels, channel_cursor, source_channels = [], 0, {}
    for stream in meta['audio']:
        source_channels[stream['index']] = []
        for channel in range(stream['channels']):
            channel_cursor += 1
            source_channels[stream['index']].append(dict(source_channel=channel_cursor, stream=stream['index'], channel=channel + 1))
    for stream in plan['audio']:
        channels.extend(source_channels[stream['index']])
    element(audio, 'channelcount', len(channels))
    audio_tracks = [element(audio, 'track') for _ in channels]
    source = ET.Element('file', id='leonida-source')
    element(source, 'name', Path(project['path']).name)
    element(source, 'pathurl', Path(project['path']).resolve().as_uri())
    rate(source, nominal, ntsc); element(source, 'duration', media_duration)
    source_tc = element(source, 'timecode'); rate(source_tc, nominal, ntsc)
    element(source_tc, 'string', '00:00:00:00'); element(source_tc, 'frame', 0); element(source_tc, 'displayformat', 'NDF')
    source_media = element(source, 'media'); source_video = element(source_media, 'video')
    source_video.append(copy.deepcopy(sample))
    source_audio = element(source_media, 'audio')
    element(source_audio, 'channelcount', channel_cursor)
    audio_sample = element(source_audio, 'samplecharacteristics')
    element(audio_sample, 'depth', 16); element(audio_sample, 'samplerate', meta['audio'][0]['sample_rate'] if meta['audio'] else 48000)
    first = True
    for row in plan['rows']:
        group = [(video_track, 'video', 1, None)] + [(track, 'audio', index + 1, c['source_channel']) for index, (track, c) in enumerate(zip(audio_tracks, channels))]
        links = []
        clipitems = []
        for track, kind, track_index, source_channel in group:
            item_id = f'clip-{row["number"]}-{kind}-{track_index}'
            item = element(track, 'clipitem', id=item_id)
            element(item, 'name', row['cut']['title']); element(item, 'enabled', 'TRUE')
            element(item, 'duration', media_duration); rate(item, nominal, ntsc)
            for field, value in [('start', row['timeline_in']), ('end', row['timeline_out']), ('in', row['source_in']), ('out', row['source_out'])]:
                element(item, field, value)
            if first:
                item.append(copy.deepcopy(source)); first = False
            else:
                element(item, 'file', id='leonida-source')
            if kind == 'audio':
                src = element(item, 'sourcetrack'); element(src, 'mediatype', 'audio'); element(src, 'trackindex', source_channel)
            comments = element(item, 'comments'); element(comments, 'clipcommenta', row['cut'].get('review_note', ''))
            links.append((item_id, kind, track_index))
            clipitems.append(item)
        for item in clipitems:
            for item_id, kind, track_index in links:
                link = element(item, 'link'); element(link, 'linkclipref', item_id); element(link, 'mediatype', kind)
                element(link, 'trackindex', track_index); element(link, 'clipindex', row['number'])
        marker = element(seq, 'marker'); element(marker, 'name', row['cut']['title'])
        element(marker, 'comment', row['cut'].get('review_note', '')); element(marker, 'in', row['timeline_in']); element(marker, 'out', -1)
    ET.indent(root, space='  ')
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(root, encoding='unicode') + '\n'
