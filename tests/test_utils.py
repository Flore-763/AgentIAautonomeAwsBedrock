"""
tests/test_utils.py
=====================

Module pur, sans dépendance externe : aucun mock nécessaire.
"""

import time
from datetime import datetime
from decimal import Decimal

import pytest

from utils import (
    decimal_default,
    generate_timestamp,
    generate_uuid,
    get_expiration_time,
    to_decimal_list,
)


class TestExpiration:
    def test_expiration_environ_30_jours_dans_le_futur(self):
        before = int(time.time())
        expiration = get_expiration_time()
        thirty_days = 30 * 24 * 60 * 60
        assert thirty_days - 2 <= expiration - before <= thirty_days + 2

    def test_expiration_est_un_entier(self):
        assert isinstance(get_expiration_time(), int)


class TestDecimalDefault:
    def test_decimal_entier_devient_int(self):
        assert decimal_default(Decimal("42")) == 42
        assert isinstance(decimal_default(Decimal("42")), int)

    def test_decimal_flottant_devient_float(self):
        assert decimal_default(Decimal("3.14")) == 3.14
        assert isinstance(decimal_default(Decimal("3.14")), float)

    def test_type_non_supporte_leve_type_error(self):
        with pytest.raises(TypeError):
            decimal_default(object())


class TestToDecimalList:
    def test_convertit_chaque_element_en_decimal(self):
        result = to_decimal_list([0.1, 0.2, -1.5])
        assert all(isinstance(x, Decimal) for x in result)

    def test_preserve_les_valeurs(self):
        result = to_decimal_list([0.1, 0.2])
        assert result == [Decimal("0.1"), Decimal("0.2")]

    def test_liste_vide(self):
        assert to_decimal_list([]) == []


class TestTimestampEtUuid:
    def test_generate_timestamp_est_un_iso_8601_valide(self):
        ts = generate_timestamp()
        # Ne doit pas lever d'exception : c'est un ISO 8601 valide.
        datetime.fromisoformat(ts)

    def test_generate_timestamp_est_en_utc(self):
        ts = generate_timestamp()
        assert ts.endswith("+00:00")

    def test_generate_uuid_est_unique(self):
        assert generate_uuid() != generate_uuid()

    def test_generate_uuid_format(self):
        value = generate_uuid()
        assert len(value) == 36
        assert value.count("-") == 4
