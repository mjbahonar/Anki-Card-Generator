"""Vocabulary images with configurable provider fallback and local Anki media."""
import base64
import html
from io import BytesIO
import json
from urllib.parse import quote, urljoin, urlparse
from bs4 import BeautifulSoup
from PIL import Image
from app.lexin_scraper import audio_filename

# Wikimedia's robot policy rejects generic browser User-Agents ("Too many requests", HTTP 403).
WIKIMEDIA_HEADERS = {'User-Agent': 'Meaning-Ankidroid/vocabulary-cards (personal study tool) python-requests'}


def wikimedia_headers(url):
    host = url.split('/', 3)[2] if url.startswith(('http://', 'https://')) else ''
    return WIKIMEDIA_HEADERS if host == 'wikimedia.org' or host.endswith('.wikimedia.org') else None


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
        response = ctx.fetch('https://commons.wikimedia.org/w/api.php?' + params + quote(word + ' filetype:bitmap', safe=''),
                             headers=WIKIMEDIA_HEADERS)
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
    if provider == 'bing':
        # Bing's result page lists each image as <a class="iusc" m='{"murl": full image, "purl": page, "t": title}'>.
        # Images belong to the pages they come from (no license data): suitable for personal study material.
        # " clipart" (as for Google) favours clear, simple pictures of the thing itself.
        url = 'https://www.bing.com/images/search?form=HDRSC2&adlt=strict&q=' + quote(word + ' clipart', safe='')
        # Bing sometimes serves a lighter page variant without result data; one retry usually gets the full page.
        for _ in range(2):
            soup = BeautifulSoup(ctx.fetch(url).text, 'html.parser')
            anchors = soup.select('a.iusc[m]')
            if anchors:
                break
        results = []
        for anchor in anchors:
            try:
                meta = json.loads(html.unescape(anchor['m']))
            except ValueError:
                continue
            src = meta.get('murl') or meta.get('turl') or ''
            if not src.startswith(('https://', 'http://')):
                continue
            page = meta.get('purl', '')
            site = urlparse(page).netloc.removeprefix('www.') if page else ''
            results.append((src, ' | '.join(part for part in ['Bing Images', site, page] if part)))
        if not results:
            text = soup.get_text(' ', strip=True).lower()
            raise ValueError('Bing blocked automated image search on this network' if 'captcha' in text
                             else 'Bing returned no usable images')
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
                    headers = wikimedia_headers(src)
                    data = (ctx.fetch(src, headers=headers) if headers else ctx.fetch(src)).content
                else:
                    continue
                with Image.open(BytesIO(data)) as image:
                    if min(image.size) < 64:
                        continue
                    ctx.archive_image(src, data, image.format, caption)
                    image.thumbnail((800, 800))
                    filename = audio_filename(word, 'image_' + provider, ctx.language).removesuffix('.mp3') + f'_{len(markup)}.png'
                    ctx.images_dir.mkdir(parents=True, exist_ok=True)
                    path = ctx.images_dir / filename
                    image.convert('RGBA' if 'A' in image.getbands() else 'RGB').save(path, format='PNG')
                ctx.register_media(path)
                markup.append('<div class="image-result"><img src="' + filename + '" alt="' + html.escape(word, quote=True)
                              + '"><div class="image-credit">' + html.escape(caption) + '</div></div>')
            except Exception as exc:
                ctx.issue(word, 'images_' + provider, exc)
        if len(markup) >= count:
            break
    if not markup:
        raise ValueError('No images downloaded from configured providers')
    return ''.join(markup)
