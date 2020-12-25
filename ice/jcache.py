# Updated cache script based on mcadmin.
# Includes timelog toggle so dates are not
# logged at all.
import json
import time
import sys
import errno
from pathlib import Path
import re

class JCache:
    def __init__(self, cachename='default', cachefolder='.jcache/', timelog=False):
        self.cachefolder = cachefolder
        self.timelog = timelog
        self.filename = re.sub(r'@"^[\w\-. ]+$";', '', cachename)
        try:
            Path(cachefolder).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    def stash(self, key, data):
        today = time.strftime("%x")
        try:
            with open(self.cachefolder + self.filename + ".json", encoding="UTF-8") as cache:
                _cache = json.load(cache)
        except:
            _cache = {}

        if self.timelog:
            _cache[today][key] = data
        else:
            _cache[key] = data

        with open(self.cachefolder + self.filename + ".json", "w", encoding="UTF-8") as cache:
            json.dump(_cache, cache, indent=4)


    def fetch(self, key, range="today"):
        today = time.strftime("%x")
        try:
            with open(self.cachefolder + self.filename + ".json", encoding="UTF-8") as cache:
                _data = json.load(cache)

            if self.timelog:
                if range == "today":
                    return _data[today][key]
                if range == "all":
                    return _data[key]
                else:
                    return _data[range][key]
            else:
                return _data[key]
        except Exception:
            raise Exception("Cache with key " + key + " not found in Cachfolder " + self.cachefolder)
