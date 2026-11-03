from .base import SourceResult
from .bangumi import BangumiAdapter, parse_bangumi_payload
from .bgmlist import BgmlistAdapter, parse_bgmlist_payload
from .yuc import YucAdapter, parse_yuc_html
from .acgsecrets import AcgSecretsAdapter, parse_acgsecrets_html
from .youranimes import YourAnimesAdapter, parse_youranimes_html

__all__ = [
    "SourceResult",
    "BangumiAdapter",
    "BgmlistAdapter",
    "YucAdapter",
    "AcgSecretsAdapter",
    "YourAnimesAdapter",
    "parse_bangumi_payload",
    "parse_bgmlist_payload",
    "parse_yuc_html",
    "parse_acgsecrets_html",
    "parse_youranimes_html",
]
