import re

from bs4 import BeautifulSoup
import requests

__all__ = (
    'Pixiv',
    'PixivObject',
    'Member',
    'Work',
    'Illust',
    'Manga',
    'Ugoira',
    'Novel',
    'Tag',
    'DictionaryArticle',
)

DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 6.3; WOW64)' \
                     'AppleWebKit/537.36 (KHTML, ' \
                     'like Gecko) Chrome/35.0.1916.153 Safari/537.36'
MAIN_PAGE = 'http://www.pixiv.net/'
LOGIN_PAGE = 'http://www.pixiv.net/login.php'
MEDIUM_ILLUST_PAGE = 'http://www.pixiv.net/member_illust.php?' \
                     'mode=medium&illust_id={illust_id}'

WORK_URL_REGEX = re.compile(r'/member_illust\.php\?mode=medium&'
                            r'illust_id=([0-9]+)')
MANGA_URL_REGEX = re.compile(r'member_illust\.php\?mode=manga&'
                             r'illust_id=([0-9]+)')
USERID_REGEX = re.compile(r'pixiv\.context\.userId\s+=\s+"([0-9]+)";')


class Pixiv:
    def __init__(
        self, id, password, *, user_agent=DEFAULT_USER_AGENT, headers=None
    ):
        self._session = requests.Session()
        self._session.headers.update(
            {
                'User-Agent': user_agent,
                'DNT': '1',
            }
        )

        if headers is not None:
            if isinstance(headers, dict):
                self._session.headers.update(headers)
            else:
                raise TypeError('Additional headers must be given in dict.')

        self.login(id, password)

    def login(self, id, password):
        self._session.get(MAIN_PAGE)
        self._session.post(
            LOGIN_PAGE,
            data={
                'mode': 'login',
                'return_to': '/',
                'pixiv_id': id,
                'pass': password,
                'skip': 1,
            },
            headers={
                'Referer': MAIN_PAGE,
            }
        )

    def member(self, id=None):
        if id is None:
            raise TypeError('You have to provide the id of the member to '
                            'retrieve their information.')
        elif not isinstance(id, int):
            raise TypeError('Member id must be given in integer form.')
        return Member(id, pixiv_session=self)


class PixivObject:
    def __init__(self, *, eager=False, pixiv_session=None):
        self._pixiv_session = pixiv_session


class Member(PixivObject):
    def __init__(self, id, *, eager=False, pixiv_session=None):
        super().__init__(eager=False, pixiv_session=pixiv_session)
        self._id = id

    @property
    def id(self):
        return self._id

    @property
    def works(self, type=None):
        all_works = []
        page_num = 1
        while True:
            response = self._pixiv_session._session.get(
                self.list_page_url(page_num, type)
            )
            soup = BeautifulSoup(response.text)
            works = soup.select(
                'ul._image-items > li.image-item > a.work'
            )
            if not works:
                break
            page_num += 1
            for work in works:
                all_works.append(
                    Work(
                        int(WORK_URL_REGEX.match(work['href']).group(1)),
                        author=self,
                        pixiv_session=self._pixiv_session
                    )
                )
        return all_works

    def list_page_url(self, page_num=None, type=None):
        list_page = 'http://www.pixiv.net/member_illust.php?'

        if type is None:
            type = 'all'
        if page_num is None:
            page_num = 1

        if page_num == 1:
            if type == 'all':
                return list_page + 'id={}'.format(self._id)
            else:
                return list_page + 'type={}&id={}'.format(type, self._id)
        else:
            return list_page + 'id={}&type={}&p={}'.format(
                self._id, type, page_num
            )


class Work(PixivObject):
    def __new__(cls, *args, **kwargs):
        if cls is Work:
            if 'eager' in kwargs and kwargs['eager']:
                if 'pixiv_session' not in kwargs:
                    raise TypeError(
                        "Keyword argument 'pixiv_session' is needed "
                        "to eagerly initialize this class."
                    )
                if len(args) > 0:
                    if 'id' in kwargs:
                        raise TypeError(
                            "{0.__module__}.{0.__qualname__}() got "
                            "multiple values for argument 'id'".format(
                                cls
                            )
                        )
                    else:
                        id = args[0]
                elif 'id' in kwargs:
                    id = kwargs['id']
                else:
                    raise TypeError(
                        "{0.__module__}.{0.__qualname__}() missing "
                        "1 required positional argument: 'id'".format(
                            cls
                        )
                    )

                response = cls._initialize_details_by_id(
                    id,
                    kwargs['pixiv_session']._session
                )
                work_type = cls._get_type_from_html(response.text)

                new_work = work_type.__new__(work_type, *args, **kwargs)
                setattr(new_work, '_response',  response)
                return new_work
            else:
                return super().__new__(cls)
        else:
            return super().__new__(cls)

    def __init__(self, id, *, author=None, eager=False, pixiv_session=None):
        super().__init__(eager=False, pixiv_session=pixiv_session)
        self._id = id
        self._author = author

        if self._pixiv_session is not None and eager and \
           (not hasattr(self, '_response') or self._response is None):
            self._initialize_details()

    @staticmethod
    def _get_type_from_html(html):
        soup = BeautifulSoup(html)

        if soup.select('div._ugoku-illust-player-container'):
            return Ugoira
        elif soup.select('div.works_display > a') and \
            MANGA_URL_REGEX.match(
                soup.select('div.works_display > a')[0]['href']
        ):
            return Manga
        elif soup.select('.original-image') is not None:
            return Illust
        else:
            raise TypeError("Unhandled work type")

    @staticmethod
    def _initialize_details_by_id(id, pixiv_session):
        return pixiv_session._session.get(
            MEDIUM_ILLUST_PAGE.format(illust_id=id)
        )

    def _initialize_details(self):
        if self._pixiv_session is None:
            raise TypeError(
                'Pixiv session should be set to initialize details.'
            )
        if not hasattr(self, '_response') or self._response is None:
            self._response = self.__class__._initialize_details_by_id(
                self._id,
                self._pixiv_session
            )

    def resolve_type(self):
        self._initialize_details()
        self.__class__ = self.__class__._get_type_from_html(
            self._response.text
        )
        self.__init__(self.id, eager=True, pixiv_session=self._pixiv_session)
        return self

    @property
    def id(self):
        return self._id

    @property
    def author(self):
        if not hasattr(self, '_author') or self._author is None:
            self._initialize_details()
            self._author = Member(
                int(USERID_REGEX.search(self._response.text).group(1)),
                pixiv_session=self._pixiv_session
            )
        return self._author

    @property
    def tags(self):
        if not hasattr(self, '_tags') or self._tags is None:
            self._initialize_details()
            soup = BeautifulSoup(self._response.text)
            self._tags = []
            for tag in soup.select(
                'span.tags-container > ul.tags > li.tag > a.text'
            ):
                self._tags.append(Tag(tag.text.strip()))

        return self._tags


class Illust(Work):
    @property
    def original_illust_url(self):
        if not hasattr(self, '_original_illust_url') or \
           self._original_illust_url is None:
            self._initialize_details()
            soup = BeautifulSoup(self._response.text)
            self._original_illust_url = \
                soup.select('img.original-image')[0].attrs['data-src']
        return self._original_illust_url

    @property
    def original_illust(self):
        if not hasattr(self, '_original_illust') or \
           self._original_illust is None:
            self._initialize_details()
            response = self._pixiv_session._session.get(
                self.original_illust_url,
                headers={
                    'Referer': MEDIUM_ILLUST_PAGE.format(illust_id=self.id),
                })
            self._original_illust = response.content
        return self._original_illust


class Manga(Work):
    pass


class Ugoira(Work):
    pass


class Novel(Work):  # Note: in pixiv, internally, novel is not handled as work
    pass


class Tag(PixivObject):
    def __init__(self, text, *, eager=False, pixiv_session=None):
        super().__init__(eager=False, pixiv_session=pixiv_session)
        self._text = text

    @property
    def text(self):
        return self._text

    @property
    def dictionary_article(self):
        return self._dictionary_article


class DictionaryArticle:
    pass
