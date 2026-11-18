import pytest
from backend.transcripts import parse, timestamp, srt


@pytest.mark.parametrize('raw,expected', [('12.5', 12.5), ('00:01:02,500', 62.5), ('01:30', 90), ('00:00:01:15', 1.5), ('02:00:00', 7200)])
def test_timestamp(raw, expected):
    assert timestamp(raw, 30) == expected


@pytest.mark.parametrize('raw', ['NaN', 'inf', '-1', '00:60:01', '00:00:01:30', '00:00:01;15', 'garbage', '1:2:3:4:5'])
def test_invalid_timestamp(raw):
    with pytest.raises(ValueError):
        timestamp(raw, 30)


def test_srt_multiline_and_roundtrip():
    segments = parse('\ufeff1\r\n00:00:00,125 --> 00:00:01,500\r\nOlá\r\nSegunda linha\r\n\r\n2\r\n00:00:02,000 --> 00:00:03,000\r\nFim', '.srt', 6, 30)
    assert segments[0]['text'] == 'Olá\nSegunda linha'
    assert parse(srt(segments), '.srt', 6, 30) == segments


@pytest.mark.parametrize('text', ['Start,End,Text\n00:00:01:15,00:00:02:00,"Olá, mundo"', 'Início;Fim;Texto\n1,5;2,0;Olá'])
def test_csv_premiere(text):
    rows = parse(text, '.csv', 6, 30)
    assert rows[0]['start'] == 1.5
    assert rows[0]['end'] == 2


@pytest.mark.parametrize('text,extension', [('1\n00:00:02,000 --> 00:00:01,000\nInválido', '.srt'), ('1\n00:00:01,000 --> 00:00:09,000\nFora', '.srt'), ('broken', '.srt'), ('Start,End,Text\n0,1,', '.csv'), ('A,B,C\n0,1,oi', '.csv'), ('', '.csv')])
def test_reject_invalid_intervals_and_headers(text, extension):
    with pytest.raises(ValueError):
        parse(text, extension, 6, 30)


def test_sort_preserves_legitimate_overlapping_subtitles():
    rows = parse('Start,End,Text\n2,4,segunda voz\n1,3,primeira voz', '.csv', 6, 30)
    assert rows[0]['start'] == 1
    assert len(rows) == 2
