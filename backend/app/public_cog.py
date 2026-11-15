"""Credential-free, bounded HTTP Range access for allowlisted public COGs."""
import io
import re
import time
from urllib.parse import urlsplit
import requests

HOSTS={'e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com',
       'esa-worldcover.s3.eu-central-1.amazonaws.com'}


def public_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.query or p.fragment or p.port not in (None,443):
        raise ValueError('Only documented, unsigned public COG assets are accepted.')
    return url


class Budget:
    def __init__(self,max_bytes=96*1024*1024,seconds=240):
        self.limit=max_bytes;self.bytes=0;self.requests=0;self.started=time.monotonic();self.seconds=seconds
        self.evidence=[]

    def check(self,size=0):
        if self.bytes+size>self.limit or time.monotonic()-self.started>self.seconds:
            raise OSError('Public subset transfer/time budget exceeded.')


class RangeFile(io.RawIOBase):
    """Rasterio opener callback; rejects a server returning an entire product."""
    def __init__(self,url,budget):
        super().__init__();self.url=public_url(url);self.budget=budget;self.position=0;self.blocks={}
        self.session=requests.Session();self.session.trust_env=False
        budget.check()
        with self.session.head(self.url,timeout=(6,15),allow_redirects=False) as response:
            budget.requests+=1
            if response.status_code!=200 or not response.headers.get('Content-Length','').isdigit():
                raise OSError('Public COG metadata request failed; redirects are not followed.')
            self.length=int(response.headers['Content-Length'])
        self.evidence={'url':url,'remote_size':self.length,'transferred_bytes':0,'ranges':0}
        budget.evidence.append(self.evidence)

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self,offset,whence=0):
        position=offset+(self.position if whence==1 else self.length if whence==2 else 0)
        if position<0: raise OSError('Negative remote seek.')
        self.position=position;return position

    def read(self,size=-1):
        if size<0: raise OSError('Whole-product reads are disabled.')
        if size==0 or self.position>=self.length:return b''
        size=min(size,self.length-self.position)
        if size>8*1024*1024: raise OSError('Oversized range read rejected.')
        start=self.position//65536*65536
        end=min(self.length-1,((self.position+size+65535)//65536)*65536-1)
        key=(start,end)
        if key not in self.blocks:
            count=end-start+1;self.budget.check(count)
            with self.session.get(self.url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},
                                  stream=True,timeout=(6,15),allow_redirects=False) as response:
                self.budget.requests+=1
                if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.length}':
                    raise OSError('Public source must honor the exact byte range; no whole-file fallback.')
                chunks=[];received=0
                for chunk in response.iter_content(65536):
                    received+=len(chunk);self.budget.check(len(chunk));self.budget.bytes+=len(chunk)
                    if received>count:raise OSError('Range response exceeded declared bounds.')
                    chunks.append(chunk)
                if received!=count:raise OSError('Truncated range response.')
                self.evidence['transferred_bytes']+=received;self.evidence['ranges']+=1
                # One read block retained; total source data is never held/downloaded.
                self.blocks={key:b''.join(chunks)}
        block=self.blocks[key];offset=self.position-start;self.position+=size
        return block[offset:offset+size]

    def close(self):
        if not self.closed:self.session.close()
        super().close()


def opener(url,budget,name='asset.tif'):
    def open_file(path,mode='rb'):
        if path!=name or mode not in ('r','rb'):raise FileNotFoundError('Only the selected public asset is readable.')
        return RangeFile(url,budget)
    return open_file
