#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate podcast-enhanced RSS feeds."""

from __future__ import absolute_import, print_function, unicode_literals

import os

try:
    from urlparse import urljoin, urlparse
except ImportError:
    from urllib.parse import urljoin, urlparse  # NOQA

import requests

from feedgen.feed import FeedGenerator

from nikola import utils
from nikola.nikola import _enclosure as _nikola_enclosure
from nikola.plugin_categories import Task
from nikola.utils import TranslatableSetting

import micawber

from archiveorg.provider import register


providers = register(registry=micawber.bootstrap_basic())


def get_enclosure_metadata(url):
    """Get metadata for enclosure."""
    return providers.request(url)


def get_enclosure_size(url, default=0):
    """Determine size (in bytes) of enclosure."""
    base_url = 'https://archive.org/'
    return requests.head(urljoin(base_url, 'download', slug, name),
        url, allow_redirects=True).headers.get('content-length', default)


def get_enclosure_duration(url):
    data = get_enclosure_metadata(url)
    return data


def _enclosure(post, lang):
    """Add an enclosure to RSS."""
    enclosure = post.meta('enclosure', lang)
    if enclosure:
        length = get_enclosure_size(enclosure)
        url = enclosure
        mime = mimetypes.guess_type(url)[0]
        return url, length, mime


class GeneratePodcastRSS(Task):
    """Generate podcast-enhanced RSS feeds."""

    name = "generate_podcast_rss"

    def set_site(self, site):
        """Set Nikola site."""
        site.register_path_handler('podcast_rss', self.rss_path)
        self.config = {
            'PODCAST_RSS_PATH': "podcast.xml",
            'PODCAST_POST_CATEGORY': "podcast",
            # None means: same as BLOG_TITLE  # (translatable)
            'PODCAST_CHANNEL_TITLE': None,
            # None means: same as SITE_URL
            'PODCAST_CHANNEL_LINK': None,
            # None means: same as BLOG_DESCRIPTION  # (translatable)
            'PODCAST_CHANNEL_DESCRIPTION': None,
            # None means: {'name': BLOG_AUTHOR, 'email': BLOG_EMAIL}
            'PODCAST_CHANNEL_AUTHOR': None,
            # Specify category hierarchy as a tuple/list of categories
            # If None, no category element is generated  # (translatable)
            'PODCAST_CHANNEL_CATEGORY': None,
            'PODCAST_CHANNEL_LOGO': None
        }

        self.config.update(site.config)

        for suffix in ('CATEGORY', 'DESCRIPTION', 'TITLE'):
            name = 'PODCAST_CHANNEL_' + suffix
            self.config[name] = TranslatableSetting(name, self.config[name],
                                                    site.config['TRANSLATIONS'])

        return super(GeneratePodcastRSS, self).set_site(site)

    def gen_tasks(self):
        """Generate RSS feeds."""
        site = self.site
        cfg = self.config
        site.scan_posts()
        yield self.group_task()

        for lang in cfg["TRANSLATIONS"]:
            feed_url = urljoin(cfg['BASE_URL'], site.link("podcast_rss", None, lang).lstrip('/'))
            output_name = os.path.join(cfg['OUTPUT_FOLDER'], site.path("podcast_rss", None, lang))
            deps = []
            deps_uptodate = []

            posts = [p for p in site.posts
                if p.meta[lang]['category'] == cfg['PODCAST_POST_CATEGORY']
            ][:cfg['FEED_LENGTH']]

            for post in posts:
                deps.extend(post.deps(lang))
                deps_uptodate.extend(post.deps_uptodate(lang))

            task = {
                'basename': self.name,
                'name': os.path.normpath(output_name),
                'file_dep': deps,
                'targets': [output_name],
                'actions': [
                    (self.render_podcast_rss, (lang, posts, output_name, feed_url))
                ],
                'task_dep': ['render_posts'],
                'clean': True,
                # XXX: Check for configuration changes with util.config_changed
                'uptodate': deps_uptodate,
            }
            yield utils.apply_filters(task, cfg['FILTERS'])

    def rss_path(self, name, lang):
        """A link to the podcast RSS feed path.

        Example:

        link://podcast => /blog/podcast.xml

        """
        return [_f for _f in (self.config['TRANSLATIONS'][lang],
                              self.config['PODCAST_RSS_PATH']) if _f]


    def render_podcast_rss(self, lang, posts, output_name, feed_url):
        """Generate the RSS XML."""
        cfg = self.config
        fg = FeedGenerator()
        fg.load_extension('podcast')

        title = cfg['PODCAST_CHANNEL_TITLE'](lang) or cfg['BLOG_TITLE'](lang)
        fg.id(feed_url)
        fg.title(title)
        fg.link(href=cfg['PODCAST_CHANNEL_LINK'] or cfg['SITE_URL'],
                title=title, rel='alternate')
        fg.link(href=feed_url, rel='self')
        fg.description(cfg['PODCAST_CHANNEL_DESCRIPTION'](lang) or
                       cfg['BLOG_DESCRIPTION'](lang))
        fg.author(cfg['PODCAST_CHANNEL_AUTHOR'] or
                  dict(name=cfg['BLOG_AUTHOR'](lang), email=cfg['BLOG_EMAIL']))
        fg.language(lang)
        fg.generator('Nikola Podcast RSS Plug-in',
                     uri='https://plugins.getnikola.com/#podcast_rss')

        if cfg['PODCAST_CHANNEL_CATEGORY'](lang):
            fg.category("/".join(cfg['PODCAST_CHANNEL_CATEGORY'](lang)))
            fg.podcast.itunes_category(*cfg['PODCAST_CHANNEL_CATEGORY'](lang))

        if cfg['PODCAST_CHANNEL_LOGO'] or cfg['LOGO_URL']:
            fg.icon(cfg['PODCAST_CHANNEL_LOGO'] or cfg['LOGO_URL'])
            fg.logo(cfg['PODCAST_CHANNEL_LOGO'] or cfg['LOGO_URL'])

        for i, post in enumerate(posts):
            content = post.text(lang,
                teaser_only=cfg["FEED_TEASERS"],
                strip_html=cfg["FEED_PLAIN"],
                feed_read_more_link=cfg["FEED_READ_MORE_LINK"],
                feed_links_append_query=cfg["FEED_LINKS_APPEND_QUERY"])
            link = post.permalink(lang, absolute=True)
            author_name, author_email = self.get_author_info(post, lang)
            fe = fg.add_entry()
            #fe.id(link)
            fe.title(post.title(lang))
            fe.content(content)
            fe.summary(post.description(lang))
            fe.link(href=link, rel='alternate')
            fe.published(post.date if post.date.tzinfo else
                       post.date.astimezone(site.tzinfo))

            if author_name or author_email:
                fe.author(name=author_name, email=author_email)

        fg.rss_file(output_name, pretty=True)

    def get_author_info(self, post, lang=None):
        """Extract author name and email from post."""
        return post.author(lang), post.meta[lang].get('email')


def main(args=None):
    pass


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]) or 0)
