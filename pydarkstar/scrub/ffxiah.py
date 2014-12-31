"""
.. moduleauthor:: Adam Gagorik <adam.gagorik@gmail.com>
"""
import pydarkstar.scrub.scrubber
import warnings
import pickle
import re
import os

class FFXIAHScrubber(pydarkstar.scrub.scrubber.Scrubber):
    """
    Get item data from ffxiah.com
    """
    def __init__(self, *args, **kwargs):
        super(FFXIAHScrubber, self).__init__(*args, **kwargs)

        # regular expressions
        self._regex_category = re.compile(r'/browse/(\d+)/?.*')
        self._regex_item     = re.compile(r'/item/(\d+)')
        self._regex_name     = re.compile(r'(.*?)\s*-?\s*(FFXIAH)?\.(com)?')

        # pickled file names
        self._pkl_item_ids = 'scrub_item_list.pkl'
        self._pkl_item_dat = 'scrub_item_info.pkl'

    def scrub(self, force=False, threads=-1, urls=None, ids=None):
        """
        Get item metadata main function.

        If the pkl files exist (from a previous run of this function), then the ids and/or data
        will just be loaded from those pkl files.  The force option allows you to ignore the
        pkl files and just redownload the data.

        The item ids can be loaded from category urls or simply passed as a list.  The urls
        can be generated automatically, in which case all possible items will be downloaded.

        :param force: ignore existing data and redownload
        :param threads: number of cpu threads to use while downloading
        :param urls: list of category urls
        :param ids: set of item ids

        :type force: bool
        :type threads: int
        :type urls: list
        :type ids: set
        """
        # force a redownload of all data
        if force:
            self.debug('forcing redownload of data')

            # get ids
            if ids is None:
                # get urls
                if urls is None:
                    urls = self._get_category_urls()
                self.debug('# urls = %d', len(urls))

                ids = self._get_itemids(urls)

                # save to file
                self._save_item_ids(ids)

            else:
                self.debug('using passed ids')
                ids = set(ids)

                if not urls is None:
                    warnings.warn('passed urls ignored')

            # from internet
            data = self._get_item_data(ids, threads=threads)

            # save to file
            self._save_item_dat(data)

            self.debug('# ids = %d', len(ids))
            self.debug('# data = %d', len(data))
            return data

        else:
            # data exists already
            if os.path.exists(self._pkl_item_dat):
                data = self._load_item_dat()

                if not ids is None:
                    warnings.warn('passed ids ignored')

                if os.path.exists(self._pkl_item_ids):
                    warnings.warn('%s ignored', self._pkl_item_ids)

                self.debug('# data = %d', len(data))
                return data

            # get ids
            if ids is None:

                # from file
                if os.path.exists(self._pkl_item_ids):
                    ids = self._load_item_ids()

                # from internet
                else:
                    # get urls
                    if urls is None:
                        urls = self._get_category_urls()
                    self.debug('# urls = %d', len(urls))

                    ids = self._get_itemids(urls)

                    # save to file
                    self._save_item_ids(ids)
            else:
                self.debug('using passed ids')
                ids = set(ids)

                if not urls is None:
                    warnings.warn('passed urls ignored')

            # from file
            if os.path.exists(self._pkl_item_dat):
                raise RuntimeError('%s exists', self._pkl_item_dat)

            # from internet
            data = self._get_item_data(ids, threads=threads)

            # save to file
            self._save_item_dat(data)

            self.debug('# ids = %d', len(ids))
            self.debug('# data = %d', len(data))
            return data

        raise RuntimeError('can not load data')

    def _load_item_ids(self):
        """
        Load item ids from pkl file.
        """
        if not os.path.exists(self._pkl_item_ids):
            return set()

        self.debug('load %s', self._pkl_item_ids)
        with open(self._pkl_item_ids, 'rb') as handle:
            ids = pickle.load(handle)
        return set(ids)

    def _load_item_dat(self):
        """
        Load item dat from pkl file.
        """
        if not os.path.exists(self._pkl_item_dat):
            return dict()

        self.debug('load %s', self._pkl_item_dat)
        with open(self._pkl_item_dat, 'rb') as handle:
            dat = pickle.load(handle)
        return dict(dat)

    def _save_item_ids(self, ids):
        """
        save item ids to pkl file.
        """
        self.debug('save %s', self._pkl_item_ids)
        with open(self._pkl_item_ids, 'wb') as handle:
            pickle.dump(ids, handle, pickle.HIGHEST_PROTOCOL)

    def _save_item_dat(self, dat):
        """
        save item dat to pkl file.
        """
        self.debug('save %s', self._pkl_item_dat)
        with open(self._pkl_item_dat, 'wb') as handle:
            pickle.dump(dat, handle, pickle.HIGHEST_PROTOCOL)

    # step 1
    def _get_category_urls(self):
        """
        Parse http://www.ffxiah.com/browse to get URLs of the
         form http://www.ffxiah.com/{CategoryNumber}
        """
        self.debug('getting category urls')

        # the browse section of FFXIAH has a list of urls with category numbers
        soup = self.soup('http://www.ffxiah.com/browse')
        urls = []
        for tag in soup.find_all('a'):
            if tag.has_attr('href'):
                href = tag.get('href')
                match = self._regex_category.match(href)
                if match:
                    try:
                        category = int(match.group(1))

                        if category < 240:
                            urls.append('http://www.ffxiah.com{href}'.format(href=href))
                            self.debug('category %s', href)
                        else:
                            self.debug('skipping %s', href)

                    except (ValueError, IndexError):
                        self.exception('failed to extract category')
                else:
                    self.debug('ignoring %s', href)

        # sort the urls
        urls.sort(key=lambda x : map(float, re.findall('\d+', x)))

        return urls

    # step 2
    def _get_itemids(self, urls):
        """
        Scrub urls of the form http://www.ffxiah.com/{CategoryNumber} for itemids.

        :param urls: category urls
        """
        self.info('getting itemids')

        items = set()
        for i, url in enumerate(urls):
            self.info('category %02d/%02d', i + 1, len(urls))
            items.update(self._get_itemids_for_category_url(url))

        return items

    # step 2.1
    def _get_itemids_for_category_url(self, url):
        """
        Scrub url of the form http://www.ffxiah.com/{CategoryNumber} for itemids.

        :param url: category url
        """
        # create tag soup
        soup = self.soup(url)

        # look for table class
        table = soup.find('table', class_='stdlist')
        if not table:
            self.error('failed to parse <table>')
            return set()

        # look for table body
        tbody = table.find('tbody')
        if not tbody:
            self.error('failed to parse <tbody>')
            return set()

        # look for table rows
        trs = tbody.find_all('tr')
        if not trs:
            self.error('failed to parse <tr>')
            return set()

        # loop table rows
        items = set()
        for j, row in enumerate(trs):

            # look for href
            href = row.find('a').get('href')

            if not href is None:
                # make sure href matches /item/{number}
                try:
                    item = int(self._regex_item.match(href).group(1))
                    items.add(item)
                    #logging.debug('found %s', href)

                except (ValueError, IndexError):
                    self.exception('failed to extract itemid!\n\n\trow %d of %s\n\n%s\n\n',
                        j, url, row)
            else:
                self.error('failed to extract href!\n\n\trow %d of %s\n\n%s\n\n',
                    j, url, row)

        # make sure we found something
        if not items:
            self.error('could not find any itemids!')
            return set()

        return items

    # step 3
    def _get_item_data(self, itemids, threads=-1):
        """
        Get metadata for many items.

        :param itemids: item numbers
        :param threads: number of cpu threads to use

        :type itemids: list
        :type threads: int
        """
        self.info('getting data')
        self.info('threads = %d', threads)

        # get data from itemids
        if threads > 1:
            from multiprocessing.dummy import Pool as ThreadPool
            pool = ThreadPool(threads)
            data = pool.map(self._get_item_data_for_itemid, itemids)
            data = {d['itemid'] : d for d in data}
        else:
            data = {}
            for i, itemid in enumerate(itemids):
                data[itemid] = self._get_item_data_for_itemid(itemid)

        return data

    # step 3.1
    def _get_item_data_for_itemid(self, itemid):
        """
        Get metadata for single item.

        :param itemid: item number
        :type itemid: int
        """
        data = {'name' : None, 'itemid' : itemid}
        url = self._create_item_url(itemid)

        # create tag soup
        soup = self.soup(url)

        # extract name
        try:
            data.update(name=self._regex_name.match(soup.title.text).group(1))
        except AttributeError:
            data.update(name=None)

        # extract numbers
        for tag in soup.find_all('span', 'number-format'):
            try:
                key = tag.parent.find_previous_sibling().text.lower()
                data[key] = int(float(tag.text))
            except (AttributeError, ValueError):
                pass

        # fix key
        data = self._fix_stack_price_key(data)

        return data

    # step 3.1.1
    @staticmethod
    def _create_item_url(itemid):
        """
        Create URL from itemid.

        :param itemid: item number
        :type itemid: int
        """
        return 'http://www.ffxiah.com/item/{item}'.format(item=itemid)

    # step 3.1.2
    @staticmethod
    def _fix_stack_price_key(data):
        """
        Fix dictionary key.

        :param data: dictionary
        :type data: dict
        """
        old_key = u'stack\xa0price'
        new_key = r'stack price'
        if data.has_key(old_key):
            data[new_key] = data[old_key]
            del data[old_key]

        return data

if __name__ == '__main__':
    pass