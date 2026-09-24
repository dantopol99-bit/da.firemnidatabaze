"""Stahování dat z veřejného REST API ARES.

Pro každé IČO se stahují dvě odpovědi:
  * ekonomicke-subjekty     – základní záznam (aktuální stav ze všech registrů),
  * ekonomicke-subjekty-vr  – výpis z veřejného (obchodního) rejstříku s historií.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

ARES_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
ENDPOINT_ZAKLAD = "ekonomicke-subjekty"
ENDPOINT_VR = "ekonomicke-subjekty-vr"
ENDPOINTY = (ENDPOINT_ZAKLAD, ENDPOINT_VR)


@dataclass
class Odpoved:
    endpoint: str
    http_status: int
    data: dict

    @property
    def nalezeno(self) -> bool:
        return self.http_status == 200 and "kod" not in self.data


def stahni(endpoint: str, ico: str, pokusy: int = 4, timeout: int = 30) -> Odpoved:
    """Stáhne jednu odpověď. 404 (subjekt není v daném registru) není chyba."""
    url = f"{ARES_URL}/{endpoint}/{ico}"
    for pokus in range(pokusy):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return Odpoved(endpoint, r.status, json.loads(r.read()))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return Odpoved(endpoint, 404, json.loads(exc.read() or b"{}"))
            if exc.code < 500 or pokus == pokusy - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if pokus == pokusy - 1:
                raise
        time.sleep(2 ** (pokus + 1))
    raise RuntimeError("nedosažitelné")


def stahni_subjekt(ico: str) -> dict[str, Odpoved]:
    return {endpoint: stahni(endpoint, ico) for endpoint in ENDPOINTY}
