"""Migrate common legacy INI options without overwriting the source or output."""
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path
import re

import yaml
from javsp.config import Cfg


def migrate(source, template):
    cfg = ConfigParser(interpolation=None)
    raw = Path(source).read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('gbk')
    cfg.read_string(text)
    data = yaml.safe_load(Path(template).read_text(encoding='utf-8'))
    warnings = []

    def get(section, key, default=''):
        return cfg.get(section, key, fallback=default).strip()

    def yes(section, key, default='no'):
        value = get(section, key, default).lower()
        if value not in ('yes', 'no', 'true', 'false', '1', '0'):
            raise ValueError(f'Invalid boolean: {section}.{key}')
        return value in ('yes', 'true', '1')

    def parts(value, delimiter=','):
        return [s.strip() for s in value.split(delimiter) if s.strip()]

    def pattern(value):
        return re.sub(r'\$([a-z]+)', r'{\1}', value)

    scan = data['scanner']
    old_patterns = parts(get('MovieID', 'ignore_regex'), ';')
    old_patterns += parts(get('MovieID', 'ignore_whole_word'), ';')
    scan['ignored_id_pattern'] = list(dict.fromkeys(old_patterns + scan['ignored_id_pattern'][:2]))
    scan['input_directory'] = get('File', 'scan_dir') or None
    extensions = parts(get('File', 'media_ext'), ';')
    if extensions:
        scan['filename_extensions'] = [s if s.startswith('.') else '.' + s for s in extensions]
    folders = parts(get('File', 'ignore_folder'), ';')
    scan['ignored_folder_name_pattern'] = [r'^\.'] + ['^' + re.escape(s) + '$' for s in folders]
    scan['minimum_size'] = get('File', 'ignore_video_file_less_than', '232') + 'MiB'
    scan['skip_nfo_dir'] = yes('File', 'skip_nfo_dir')
    scan['manual'] = False

    network = data['network']
    network['proxy_server'] = get('Network', 'proxy') if yes('Network', 'use_proxy') else None
    if not network['proxy_server']:
        network['proxy_server'] = None
    for key in network['proxy_free']:
        network['proxy_free'][key] = get('ProxyFree', key, network['proxy_free'][key])
    if network['proxy_free']['javdb'].rstrip('/').lower() == 'https://javdb368.com':
        network['proxy_free']['javdb'] = 'https://javdb.com'
        warnings.append('Outdated JavDB address changed to https://javdb.com.')
    network['retry'] = int(get('Network', 'retry', '3'))
    network['timeout'] = 'PT' + get('Network', 'timeout', '10') + 'S'

    crawler = data['crawler']
    for key in crawler['selection']:
        value = get('CrawlerSelect', key)
        if value:
            crawler['selection'][key] = parts(value)
    crawler['required_keys'] = parts(get('Crawler', 'required_keys', 'cover,title'))
    for dest, old in [('hardworking', 'hardworking_mode'), ('respect_site_avid', 'respect_site_avid'), ('normalize_actress_name', 'unify_actress_name')]:
        crawler[dest] = yes('Crawler', old)
    crawler['fc2fan_local_path'] = get('Crawler', 'fc2fan_local_path') or None
    crawler['sleep_after_scraping'] = 'PT' + get('Crawler', 'sleep_after_scraping', '0') + 'S'
    cover_choice = get('Crawler', 'ignore_javdb_cover', 'auto').lower()
    if cover_choice not in ('yes', 'no', 'auto'):
        raise ValueError('Invalid Crawler.ignore_javdb_cover')
    crawler['use_javdb_cover'] = {'yes': 'no', 'no': 'yes', 'auto': 'fallback'}[cover_choice]

    summary = data['summarizer']
    summary['move_files'] = yes('File', 'enable_file_move')
    path = summary['path']
    path['output_folder_pattern'] = pattern('/'.join(filter(None, [get('NamingRule', 'output_folder'), get('NamingRule', 'save_dir')])))
    path['basename_pattern'] = pattern(get('NamingRule', 'filename', '{num}'))
    path['length_maximum'] = int(get('NamingRule', 'max_path_len', '250'))
    path['length_by_byte'] = get('NamingRule', 'calc_path_len_by_byte', 'auto').lower() != 'no'
    path['max_actress_count'] = int(get('NamingRule', 'max_actress_count', '10'))
    path['hard_link'] = yes('File', 'use_hardlink')
    summary['title']['remove_trailing_actor_name'] = yes('Crawler', 'title__remove_actor')
    for key, old in [('title','title'),('actress','actress'),('series','serial'),('director','director'),('producer','producer'),('publisher','publisher')]:
        summary['default'][key] = get('NamingRule', 'null_for_' + old, summary['default'][key])
    summary['censor_options_representation'] = [get('NamingRule','text_for_' + x) for x in ('uncensored','censored','unknown_censorship')]
    summary['nfo']['title_pattern'] = pattern(get('NamingRule', 'nfo_title', '{num} {title}'))
    for name in ('genres', 'tags'):
        summary['nfo']['custom_' + name + '_fields'] = [pattern(x) for x in parts(get('NFO', 'add_custom_' + name + '_fields'))] if yes('NFO', 'add_custom_' + name) else []
    summary['cover']['highres'] = yes('Picture', 'use_big_cover')
    summary['cover']['add_label'] = yes('Picture', 'add_label_to_cover')
    labels = parts(get('Picture', 'use_ai_crop_labels'))
    summary['cover']['crop']['on_id_pattern'] = [r'^\d{6}[-_]\d{3}$' if x == r'\d' else '^' + x for x in labels]
    summary['cover']['crop']['engine'] = None
    if yes('Picture', 'use_ai_crop'):
        warnings.append('AI crop settings need manual review; crop is disabled.')
    summary['extra_fanarts']['enabled'] = yes('Picture', 'use_extra_fanarts')
    interval = get('Picture', 'extra_fanarts_scrap_interval', '1.5')
    summary['extra_fanarts']['scrap_interval'] = 'PT' + interval + 'S'
    data['translator']['fields'] = {key: yes('Translate', 'translate_' + key) for key in ('title', 'plot')}
    data['translator']['engine'] = None
    if get('Translate', 'engine'):
        warnings.append('Translation engine and credentials need manual review; translation is disabled.')
    if get('NamingRule', 'media_servers', 'universal') != 'universal':
        warnings.append('Legacy media server naming presets require manual review.')
    if yes('Crawler', 'title__chinese_first'):
        warnings.append('Legacy Chinese-first title behavior has no direct equivalent; review output.')
    data['other'] = {'interactive': False, 'check_update': False, 'auto_update': False}
    Cfg.model_validate(data)
    return data, warnings


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--template', type=Path, default=Path(__file__).resolve().parents[1] / 'config.yml')
    parser.add_argument('--input-directory', type=Path)
    args = parser.parse_args()
    data, warnings = migrate(args.source, args.template)
    if args.input_directory is not None:
        if not args.input_directory.is_absolute() or not args.input_directory.is_dir():
            parser.error('input directory must be an existing absolute directory')
        data['scanner']['input_directory'] = str(args.input_directory)
        Cfg.model_validate(data)
    with args.output.open('x', encoding='utf-8', newline='\n') as f:
        f.write('# Migrated from legacy INI. Review paths, proxy, and settings before use.\n')
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    for warning in warnings:
        print('WARNING:', warning)
    print('Validated configuration created:', args.output)


if __name__ == '__main__':
    main()
