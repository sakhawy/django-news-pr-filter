# NOTE: I wasted way too much time trying to do
# this with PyGitHub but failed miserably with 'search'.
# So, 'gh' CLI was the way to go.
# It's also the reason why the code is messy :D

import argparse
import dataclasses
import datetime
import json
import logging
import os
import subprocess
import typing
import urllib.parse

import mdutils

REPO = 'django/django'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, 'OUT.md')
# number of PRs per page.
# FIXME: implement pagination
# if django started to average more
# than 200 merged PRs per week :D 
PRS_LIMIT = 200

logging.basicConfig(
    format="[%(asctime)s - %(name)s - %(levelname)s]: %(message)s",
)
logger = logging.getLogger('main')
logger.setLevel(level=logging.DEBUG)


def parse_date(datestr):
    try:
        return datetime.date.fromisoformat(datestr)
    except:
        raise argparse.ArgumentTypeError(
            f'Invalid date format {datestr}. Should be "YYYY-MM-DD".'
        )


def send_command(command):
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE
    )
    logger.debug(
        f'{command} was executed.'
    )
    output, error = process.communicate()

    if error:
        raise Exception(error)

    return json.loads(output.decode('utf-8'))


@dataclasses.dataclass
class Author:
    login: str
    name: str = dataclasses.field(default=None)
    is_new: bool = dataclasses.field(default=False)

    def get_url(self):
        return f'https://github.com/{self.login}'

    def get_name_or_login(self):
        return self.name or self.login

    def __hash__(self) -> str:
        return hash(self.login)


@dataclasses.dataclass
class File:
    path: str
    additions: int
    deletions: int


@dataclasses.dataclass
class PR:
    title: str
    number: str
    url: str
    author: Author
    files: typing.List[File]
    created: datetime.date = None
    release: str = None

    def is_release_modified(self) -> bool:
        for file in self.files:
            if 'docs/release' in file.path:
                self.release = file.path.replace('docs/releases/', '')[:-4]
                return True
        return False

    def is_old(self, date) -> bool:
        return self.created < date


@dataclasses.dataclass
class Results:
    prs: typing.List[PR] = dataclasses.field(default_factory=list)

    def get_release_prs(self) -> typing.List[PR]:
        return list(filter(
            lambda pr: pr.is_release_modified(),
            self.prs
        ))

    def get_older_prs(self, date) -> typing.List[PR]:
        return list(filter(
            lambda pr: pr.is_old(date),
            self.prs
        ))

    def get_authors(self) -> typing.List[Author]:
        return list(set(pr.author for pr in self.prs))

    def get_new_authors(self) -> typing.List[Author]:
        return list(set(pr.author for pr in self.prs if pr.author.is_new))


class DjangoNewsPRFilter:
    def __init__(
            self,
            start_date: datetime.date = None,
            end_date: datetime.date = None,
            output_file: str = OUTPUT_FILE
    ):

        self.end_date = end_date
        if not end_date:
            today = datetime.date.today()
            self.end_date = today

        self.start_date = start_date
        if not start_date:
            # one business week ago
            last_sunday = self.end_date - datetime.timedelta(days=today.weekday())
            self.start_date = last_sunday

        self.output_file = output_file

        self.results = Results()

        logger.info(
            f'Initiated the script with the following configs: '
            f'Start date = {self.start_date}, '
            f'End date = {self.end_date}, '
            f'Output file = {self.output_file}.'
        )

    def _load_prs(self) -> typing.List[Results]:
        logger.info(
            'Loading merged PRs...'
        )
        command = (
            'gh pr list --repo django/django '
            f'-S "is:pr merged:{self.start_date}..{self.end_date}" '
            f'-L {PRS_LIMIT} '
            '--json title,number,url,author,files,createdAt',
        )
        response = send_command(command)

        for item in response:
            raw_author = item.pop('author')
            author = self._create_author(raw_author)
            files = self._create_files(item.pop('files'))
            pr = self._create_pr(item, author, files)
            self.results.prs.append(pr)

        logger.info(
            f'{len(self.results.prs)} PRs and related data were loaded.'
        )

    def _create_author(self, raw_author):
        author_login = raw_author.get('login')
        author_name = raw_author.get('name')
        if author_login not in map(lambda author: author.login, self.results.get_authors()):
            is_new = self._check_new_author(login=author_login)
        else:
            is_new = list(filter(lambda author: author.login == author_login, self.results.get_authors()))[0].is_new
        return Author(login=author_login, name=author_name, is_new=is_new)

    def _create_files(self, raw_files):
        files = []
        for file in raw_files:
            file_path = file.get('path')
            file_additions = file.get('additions')
            file_deletions = file.get('deletions')
            files.append(File(path=file_path, additions=file_additions, deletions=file_deletions))
        return files

    def _create_pr(self, item, author, files):
        item_pr_number = item.get('number')
        item_pr_title = item.get('title')
        item_pr_url = item.get('url')
        item_pr_created = datetime.datetime.strptime(item.get('createdAt').split('T')[0], '%Y-%m-%d').date()
        return PR(title=item_pr_title, number=item_pr_number, url=item_pr_url, author=author, files=files,
                  created=item_pr_created)

    def _check_new_author(self, login: str) -> bool:
        # NOTE: for consistency reasons, this checks if
        # a contributor is new in a given date range -- up to
        # `self.end_time`.
        # 1970 acts as a lower bound for the filter (similar to "-inf")
        command = (
            'gh pr list --repo django/django '
            f'-S "is:pr merged:1970-01-01..{self.end_date} author:{login}" '
            '--json number'
        )

        response = send_command(command)

        if len(response) > 1:
            return False

        logger.debug(f'{login} is a new contributor!')
        return True

    def export_md(self):
        """
        Exports the data into a .md file.

        (very messy, should've just used normal file IO!)
        """
        logger.info(f'Exporting to {self.output_file}...')
        self._load_prs()
        prs = self.results.prs
        older_prs = self.results.get_older_prs(self.end_date - datetime.timedelta(days=30 * 6))
        older_prs_than_3 = self.results.get_older_prs(self.end_date - datetime.timedelta(days=30 * 3))
        authors = self.results.get_authors()
        new_authors = self.results.get_new_authors()

        logger.debug(new_authors)

        md_file = mdutils.MdUtils(file_name=self.output_file, title='Updates to Django')
        self._write_synopsis(md_file, prs, authors, new_authors)
        self._write_release_prs(md_file)
        if len(older_prs) >= 1:
            self._write_old_prs(md_file, older_prs, months=6)
        elif len(older_prs_than_3) >= 1:
            self._write_old_prs(md_file, older_prs_than_3, months=3)

        md_file.create_md_file()

        logger.info('The data was exported successfully.')

    def _write_synopsis(self, md_file, prs, authors, new_authors):
        md_file.new_header(level=1, title='Synopsis')
        search_url = f'https://github.com/{REPO}/pulls?q='
        search_url += urllib.parse.quote(
            'is:pr ' f'merged:{self.start_date}..{self.end_date}'
        )
        md_file.write(f'Last week we had ')
        md_file.write(md_file.new_inline_link(
            search_url, f'{len(prs)} pull requests'
        ))
        md_file.write(
            f' merged into Django by {len(authors)} different contributors'
        )
        if new_authors:
            self._write_new_contributors(md_file, new_authors)
        else:
            md_file.new_line()
            md_file.new_line()
            md_file.write(f' [comment]: <> (This is a comment. No new contributors :( )')

    def _latest_new_contributors(self, md_file, authors):
        md_file.write(
            md_file.new_inline_link(authors[-2].get_url(), authors[-2].get_name_or_login()))
        md_file.write(' and ')
        md_file.write(
            md_file.new_inline_link(authors[-1].get_url(), authors[-1].get_name_or_login()))

    def _write_new_contributors(self, md_file, new_authors):
        num_new_authors = len(new_authors)
        md_file.write(
            f' - including {"a" if num_new_authors == 1 else num_new_authors} first-time contributor{"s" if num_new_authors > 1 else ""}! Congratulations to ')
        if num_new_authors == 1:
            md_file.write(
                md_file.new_inline_link(new_authors[0].get_url(), new_authors[0].get_name_or_login()))

        elif num_new_authors == 2:
            self._latest_new_contributors(md_file, new_authors)

        else:
            for author in new_authors[:-2]:
                md_file.write(md_file.new_inline_link(author.get_url(), author.get_name_or_login()))
                md_file.write(', ')
            self._latest_new_contributors(md_file, new_authors)
        md_file.write(' for having their first commits merged into Django - welcome on board!')

    def _write_release_prs(self, md_file):
        md_file.new_line()
        md_file.new_header(level=1, title='PRs that modified the release file')
        for pr in self.results.get_release_prs():
            md_file.write("- ")
            md_file.write(md_file.new_inline_link(
                link=pr.url,
                text=str(pr.title)
            ))
            md_file.new_line()
            md_file.write(md_file.new_inline_link(
                link=f'https://django--{pr.number}.org.readthedocs.build/en/{pr.number}/releases/{pr.release}.html',
                text='See this PR inside the docs.'
            ))
            md_file.new_line()
            md_file.new_line()

    def _write_old_prs(self, md_file, older, months):
        md_file.new_line()
        md_file.new_header(level=1, title=f'Older PR{"S" if len(older) > 1 else ""} than {months} months')
        for pr in older:
            md_file.write("- ")
            md_file.write(md_file.new_inline_link(
                link=pr.url
            ))
            md_file.new_line()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='Django News PR Filter',
        description='Pulls info about the PRs merged into \'django/django\' last week.',
        epilog=''
    )

    parser.add_argument(
        '-s',
        '--start_date',
        type=parse_date,
        help='Filters merged PRs starting from `start_date`.'
             'e.g. 2024-01-28',
        default=None
    )
    parser.add_argument(
        '-e',
        '--end_date',
        type=parse_date,
        help='Filters merged PRs ending on `end_date`.'
             'e.g. 2024-01-28',
        default=None
    )
    parser.add_argument(
        '-o',
        '--output_file',
        type=str,
        help='Specifies the location of the output .md file.',
        default=OUTPUT_FILE
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true'
    )
    args = parser.parse_args()

    today = datetime.date.today()
    last_week_monday = today - datetime.timedelta(days=today.weekday() + 7)
    last_week_sunday = last_week_monday + datetime.timedelta(days=6)

    end_date = args.end_date
    if not end_date:
        end_date = last_week_sunday

    start_date = args.start_date
    if not start_date:
        start_date = last_week_monday

    output_file = args.output_file

    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    DjangoNewsPRFilter(
        start_date=start_date,
        end_date=end_date,
        output_file=output_file
    ).export_md()

    logger.info(
        'Done!'
    )
