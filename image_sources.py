"""Vocabulary images with configurable provider fallback and local Anki media."""
import base64
import html
from io import BytesIO
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from PIL import Image
from lexin_scraper import audio_filename


def candidates(provider, word, ctx, count):
    if provider == 'google':
        url = 'https://www.google.com/search?udm=2&q=' + quote(word + ' clipart', safe='')
        response = ctx.fetch(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(' ', strip=True).lower()
        if '/sorry/' in response.url or 'unusual traffic' in text:
            raise ValueError('Google blocked automated image search on this network')
        results = []
        for image in soup.select('img'):
            src = image.get('data-src') or image.get('src', '')
            if not src or 'googlelogo' in src.lower():
                continue
            results.append((urljoin(url, src), 'Google Images'))
        if not results:
            raise ValueError('Google returned no usable images; JavaScript or access restrictions')
        return results
    if provider == 'commons':
        params = ('action=query&generator=search&gsrnamespace=6&gsrlimit=10&prop=imageinfo'
                  '&iiprop=url%7Cextmetadata&iiurlwidth=600&format=json&gsrsearch=')
        response = ctx.fetch('https://commons.wikimedia.org/w/api.php?' + params + quote(word + ' filetype:bitmap', safe=''))
        pages = response.json().get('query', {}).get('pages', {}).values()
        results = []
        for page in sorted(pages, key=lambda item: item.get('index', 0)):
            for info in page.get('imageinfo', []):
                meta = info.get('extmetadata', {})
                def value(key):
                    raw = meta.get(key, {}).get('value', '')
                    return BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True) if '<' in raw else html.unescape(raw)
                caption = ' | '.join(part for part in [page.get('title', '').removeprefix('File:'),
                    value('Artist'), value('Credit'), value('LicenseShortName'), value('LicenseUrl'), info.get('descriptionurl')] if part)
                results.append((info.get('thumburl') or info.get('url', ''), caption))
        return results
    raise ValueError('Unknown image provider: ' + provider)


def download_images(word, ctx):
    options = ctx.config.section('sources')['images']
    count = options.get('count', 3)
    markup, seen = [], set()
    for provider in options.get('priority', ['google', 'commons']):
        try:
            results = candidates(provider, word, ctx, count)
        except Exception as exc:
            ctx.issue(word, 'images_' + provider, exc)
            continue
        for src, caption in results:
            if len(markup) >= count:
                break
            if src in seen:
                continue
            seen.add(src)
            try:
                if src.startswith('data:image/') and ';base64,' in src:
                    data = base64.b64decode(src.split(',', 1)[1], validate=True)
                elif src.startswith(('http://', 'https://')):
                    data = ctx.fetch(src).content
                else:
                    continue
                with Image.open(BytesIO(data)) as image:
                    if min(image.size) < 64:
                        continue
                    image.thumbnail((800, 800))
                    filename = audio_filename(word, 'image_' + provider, ctx.language).removesuffix('.mp3') + f'_{len(markup)}.png'
                    ctx.images_dir.mkdir(parents=True, exist_ok=True)
                    path = ctx.images_dir / filename
                    image.convert('RGBA' if 'A' in image.getbands() else 'RGB').save(path, format='PNG')
                ctx.media.add(path.resolve())
                markup.append('<div class="image-result"><img src="' + filename + '" alt="' + html.escape(word, quote=True)
                              + '"><div class="image-credit">' + html.escape(caption) + '</div></div>')
            except Exception as exc:
                ctx.issue(word, 'images_' + provider, exc)
        if len(markup) >= count:
            break
    if not markup:
        raise ValueError('No images downloaded from configured providers')
    return ''.join(markup)
