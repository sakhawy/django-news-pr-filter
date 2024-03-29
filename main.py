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


@dataclasses.dataclass
class Author:
    login: str
    name: str  = dataclasses.field(default=None)
    is_new: bool = dataclasses.field(default=False)

    def get_url(self):
        return f'https://github.com/{self.login}'

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

    def is_release_modified(self) -> bool:
        for file in self.files:
            if 'docs/release' in file.path:
                return True
        return False


@dataclasses.dataclass
class Results:
    prs: typing.List[PR] = dataclasses.field(default_factory=list)

    def get_release_prs(self) -> typing.List[PR]:
        return list(filter(
            lambda pr: pr.is_release_modified(),
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
            '--json title,number,url,author,files',
        )
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

        response = json.loads(output.decode('utf-8'))
        
        for item in response:
            raw_author = item.pop('author')
            if raw_author['login'] not in map(
                    lambda author: author.login, self.results.get_authors()):
                is_new = self._check_new_author(login=raw_author['login'])
            else:
                is_new = list(filter(
                    lambda author: author.login == raw_author['login'],
                    self.results.get_authors()))[0].is_new

            author_name = raw_author.get('name')
            author_login = raw_author.get('login')
            author = Author(
                login=author_login,
                name=author_name,
                is_new=is_new
            )

            raw_files = item.pop('files')
            files = []
            for file in raw_files:
                file_path = file.get('path')
                file_additions = file.get('additions')
                file_deletions = file.get('deletions')
                files.append(
                    File(
                        path=file_path,
                        additions=file_additions,
                        deletions=file_deletions
                    )
                )
            
            item_pr_number = item.get('number')
            item_pr_title = item.get('title')
            item_pr_url = item.get('url')
            pr = PR(
                title=item_pr_title,
                number=item_pr_number,
                url=item_pr_url,
                author=author,
                files=files,
            )
            self.results.prs.append(pr)

        logger.info(
            f'{len(self.results.prs)} PRs and related data were loaded.'
        )

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

        response = json.loads(output.decode('utf-8'))
        if len(response) > 1:
            return False
        
        logger.debug(f'{login} is a new contributor!')
        return True

    def export_md(self):
        """
        Exports the data into a .md file.
        
        (very messy, should've just used normal file IO!)
        """
        logger.info(
            f'Exporting to {self.output_file}...'
        )
        self._load_prs()
        prs = self.results.prs
        authors = self.results.get_authors()
        new_authors = self.results.get_new_authors()

        logger.debug(
            new_authors
        )

        md_file = mdutils.MdUtils(file_name=self.output_file, title='Updates to Django')
        md_file.new_header(level=1, title='Synopsis')

        # FIXME: this can get weird if we have few contributors!
        # too many edge cases and I don't have the time atm, sorry :'D
        search_url = f'https://github.com/{REPO}/pulls?q='
        search_url += urllib.parse.quote(
            'is:pr '
            f'merged:{self.start_date}..{self.end_date}'
        )
        
        md_file.write(
            f'Last week we had '
        )
        md_file.write(md_file.new_inline_link(
            search_url,
            f'{len(prs)} pull requests'
        ))
        md_file.write(
            f' merged into Django '
            f'by {len(authors)} different contributors'
        )
        if new_authors:
            md_file.write(
                f' - including {len(new_authors)} first time '
                f'contributors! Congratulations to '
            )
            for author in new_authors[:-1]:
                md_file.write(md_file.new_inline_link(
                    author.get_url(),
                    # FIXME: for some reason `gh` search doesn't returns a `author.name` 
                    author.name or author.login
                ))
                md_file.write(', ')
            author = new_authors[-1]
            md_file.write(
                'and '
            )
            md_file.write(md_file.new_inline_link(
                author.get_url(),
                # FIXME: for some reason `gh` search doesn't returns a `author.name` 
                author.name or author.login
            ))
            md_file.write(
                f' for having their first commits merged into Django - welcome on board!'
            )

        md_file.new_line()
        md_file.new_header(level=1, title='PRs that modified the release file')
        for pr in self.results.get_release_prs():
            md_file.write("- ")
            md_file.write(md_file.new_inline_link(
                link=pr.url
            ))
            md_file.new_line()

        md_file.create_md_file()

        logger.info(
            'The data was exported successfully.'
        )


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
