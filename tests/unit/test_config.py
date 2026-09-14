"""Tests for shinkoku.config — YAML config loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from shinkoku.config import (
    AddressConfig,
    BusinessConfig,
    FilingConfig,
    ShinkokuConfig,
    TaxpayerConfig,
    determine_blue_return_deduction,
    load_config,
)
from shinkoku.tools.profile import get_taxpayer_profile


CONFIRMATION_FIELDS = {
    "family": ("has_spouse", "has_dependents", "dependent_count"),
    "housing_loan": ("applicable", "first_year"),
    "estimated_tax": ("applicable", "amount"),
}


def _confirmation_values(config: ShinkokuConfig) -> dict:
    values = config.model_dump()
    return {section: values[section] for section in CONFIRMATION_FIELDS}


@pytest.mark.parametrize("section_value", ["omitted", None, {}, "null_fields"])
def test_unconfirmed_setup_sections_roundtrip(tmp_path: Path, section_value: object) -> None:
    data: dict = {"tax_year": 2026, "db_path": str(tmp_path / "not-opened.db")}
    for section, fields in CONFIRMATION_FIELDS.items():
        if section_value == "null_fields":
            data[section] = dict.fromkeys(fields)
        elif section_value != "omitted":
            data[section] = section_value
    path = tmp_path / "unconfirmed.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    original_bytes = path.read_bytes()
    expected = {section: dict.fromkeys(fields) for section, fields in CONFIRMATION_FIELDS.items()}

    config = load_config(str(path))
    profile = get_taxpayer_profile(config_path=str(path))

    assert _confirmation_values(config) == expected
    assert {section: profile[section] for section in CONFIRMATION_FIELDS} == expected
    saved = tmp_path / "saved.yaml"
    saved.write_text(yaml.safe_dump(config.model_dump()), encoding="utf-8")
    assert _confirmation_values(load_config(str(saved))) == expected
    assert path.read_bytes() == original_bytes
    assert not (tmp_path / "not-opened.db").exists()


@pytest.mark.parametrize(
    "sections",
    [
        {
            "family": {"has_spouse": False, "has_dependents": False, "dependent_count": 0},
            "housing_loan": {"applicable": False, "first_year": False},
            "estimated_tax": {"applicable": False, "amount": 0},
        },
        {
            "family": {"has_spouse": True, "has_dependents": True, "dependent_count": 2},
            "housing_loan": {"applicable": True, "first_year": False},
            "estimated_tax": {"applicable": True, "amount": 120000},
        },
        {
            "family": {"has_spouse": None, "has_dependents": False, "dependent_count": None},
            "housing_loan": {"applicable": True, "first_year": None},
            "estimated_tax": {"applicable": None, "amount": 0},
        },
    ],
)
def test_setup_values_keep_none_false_and_zero_through_profile(
    tmp_path: Path, sections: dict
) -> None:
    path = tmp_path / "confirmed.yaml"
    path.write_text(yaml.safe_dump({"tax_year": 2026, **sections}), encoding="utf-8")
    original_bytes = path.read_bytes()
    config = load_config(str(path))
    saved = tmp_path / "saved.yaml"
    saved.write_text(yaml.safe_dump(config.model_dump()), encoding="utf-8")

    profile = json.loads(json.dumps(get_taxpayer_profile(config_path=str(saved))))

    assert _confirmation_values(config) == sections
    for section, expected in sections.items():
        assert profile[section] == expected
        for field, value in expected.items():
            # PythonではFalse == 0のため、値だけでなくJSON往復後の型も検証する。
            assert type(profile[section][field]) is type(value)
    assert path.read_bytes() == original_bytes


def test_partial_setup_sections_do_not_infer_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "partial-confirmation.yaml"
    path.write_text(
        "family:\n  has_dependents: false\nhousing_loan:\n  applicable: false\n"
        "estimated_tax:\n  applicable: false\n",
        encoding="utf-8",
    )

    profile = get_taxpayer_profile(config_path=str(path))

    assert profile["family"] == {
        "has_spouse": None,
        "has_dependents": False,
        "dependent_count": None,
    }
    assert profile["housing_loan"] == {"applicable": False, "first_year": None}
    assert profile["estimated_tax"] == {"applicable": False, "amount": None}


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("family", "has_spouse", 0),
        ("family", "has_dependents", "false"),
        ("housing_loan", "applicable", 0),
        ("housing_loan", "first_year", "false"),
        ("estimated_tax", "applicable", 0),
        ("family", "dependent_count", False),
        ("family", "dependent_count", -1),
        ("estimated_tax", "amount", False),
        ("estimated_tax", "amount", "0"),
        ("estimated_tax", "amount", -1),
    ],
)
def test_setup_confirmation_types_are_not_coerced(
    tmp_path: Path, section: str, field: str, value: object
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump({section: {field: value}}), encoding="utf-8")

    with pytest.raises(ValidationError):
        load_config(str(path))


def test_example_config_keeps_setup_sections_unconfirmed(tmp_path: Path) -> None:
    template = Path(__file__).resolve().parents[2] / "shinkoku.config.example.yaml"
    path = tmp_path / "example.yaml"
    path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    profile = get_taxpayer_profile(config_path=str(path))

    assert {section: profile[section] for section in CONFIRMATION_FIELDS} == {
        section: dict.fromkeys(fields) for section, fields in CONFIRMATION_FIELDS.items()
    }


@pytest.fixture
def minimal_config_yaml(tmp_path):
    """Minimal config YAML with only tax_year and db_path."""
    config_file = tmp_path / "shinkoku.config.yaml"
    config_file.write_text(
        "tax_year: 2025\ndb_path: ./test.db\n",
        encoding="utf-8",
    )
    return config_file


@pytest.fixture
def full_config_yaml(tmp_path):
    """Full config YAML with all sections populated."""
    content = """\
tax_year: 2025
db_path: ./test.db
output_dir: ./output
taxpayer:
  last_name: 山田
  first_name: 太郎
  last_name_kana: ヤマダ
  first_name_kana: タロウ
  gender: male
  date_of_birth: "1990-01-15"
  phone: "03-1234-5678"
  my_number: "123456789012"
  widow_status: none
  disability_status: none
  working_student: false
address:
  postal_code: "100-0001"
  prefecture: 東京都
  city: 千代田区
  street: 丸の内1-1-1
  building: テストビル3F
business:
  trade_name: テスト屋
  industry_type: 情報通信業
  business_description: ソフトウェア開発
  establishment_year: 2020
filing:
  submission_method: e-tax
  return_type: blue
  blue_return_deduction: 650000
  electronic_bookkeeping: true
  tax_office_name: 麹町税務署
"""
    config_file = tmp_path / "shinkoku.config.yaml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


class TestLoadMinimalConfig:
    """後方互換: tax_year と db_path のみの最小構成で読み込めることを確認。"""

    def test_loads_tax_year(self, minimal_config_yaml):
        cfg = load_config(str(minimal_config_yaml))
        assert cfg.tax_year == 2025

    def test_loads_db_path(self, minimal_config_yaml):
        cfg = load_config(str(minimal_config_yaml))
        assert cfg.db_path == "./test.db"

    def test_returns_shinkoku_config_instance(self, minimal_config_yaml):
        cfg = load_config(str(minimal_config_yaml))
        assert isinstance(cfg, ShinkokuConfig)

    def test_sub_configs_are_defaults(self, minimal_config_yaml):
        cfg = load_config(str(minimal_config_yaml))
        assert isinstance(cfg.taxpayer, TaxpayerConfig)
        assert isinstance(cfg.address, AddressConfig)
        assert isinstance(cfg.business, BusinessConfig)
        assert isinstance(cfg.filing, FilingConfig)


class TestLoadFullConfig:
    """全セクションが記載されたフル構成を正しく読み込むことを確認。"""

    def test_taxpayer_name(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.taxpayer.last_name == "山田"
        assert cfg.taxpayer.first_name == "太郎"

    def test_taxpayer_kana(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.taxpayer.last_name_kana == "ヤマダ"
        assert cfg.taxpayer.first_name_kana == "タロウ"

    def test_taxpayer_personal_info(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.taxpayer.gender == "male"
        assert cfg.taxpayer.date_of_birth == "1990-01-15"
        assert cfg.taxpayer.phone == "03-1234-5678"

    def test_address_fields(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.address.postal_code == "100-0001"
        assert cfg.address.prefecture == "東京都"
        assert cfg.address.city == "千代田区"
        assert cfg.address.street == "丸の内1-1-1"
        assert cfg.address.building == "テストビル3F"

    def test_business_fields(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.business.trade_name == "テスト屋"
        assert cfg.business.industry_type == "情報通信業"
        assert cfg.business.business_description == "ソフトウェア開発"
        assert cfg.business.establishment_year == 2020

    def test_filing_fields(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.filing.submission_method == "e-tax"
        assert cfg.filing.return_type == "blue"
        assert cfg.filing.blue_return_deduction == 650_000
        assert cfg.filing.electronic_bookkeeping is True
        assert cfg.filing.tax_office_name == "麹町税務署"

    def test_output_dir(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.output_dir == "./output"


class TestMissingConfigFile:
    """存在しないファイルパスで FileNotFoundError が発生することを確認。"""

    def test_raises_file_not_found(self, tmp_path):
        missing_path = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_config(missing_path)

    def test_error_message_includes_path(self, tmp_path):
        missing_path = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError, match="nonexistent.yaml"):
            load_config(missing_path)


class TestDefaultValues:
    """セクションが省略された場合にデフォルト値が適用されることを確認。"""

    def test_default_tax_year(self):
        cfg = ShinkokuConfig()
        assert cfg.tax_year == 2025

    def test_default_db_path(self):
        cfg = ShinkokuConfig()
        assert cfg.db_path == "./shinkoku.db"

    def test_default_output_dir(self):
        cfg = ShinkokuConfig()
        assert cfg.output_dir == "./output"

    def test_default_taxpayer_empty_strings(self):
        cfg = ShinkokuConfig()
        assert cfg.taxpayer.last_name == ""
        assert cfg.taxpayer.first_name == ""
        assert cfg.taxpayer.last_name_kana == ""
        assert cfg.taxpayer.first_name_kana == ""
        assert cfg.taxpayer.phone == ""

    def test_default_taxpayer_none_fields(self):
        cfg = ShinkokuConfig()
        assert cfg.taxpayer.my_number is None
        assert cfg.taxpayer.gender is None
        assert cfg.taxpayer.date_of_birth is None

    def test_default_taxpayer_status_fields(self):
        cfg = ShinkokuConfig()
        assert cfg.taxpayer.widow_status == "none"
        assert cfg.taxpayer.disability_status == "none"
        assert cfg.taxpayer.working_student is False

    def test_default_address_empty(self):
        cfg = ShinkokuConfig()
        assert cfg.address.postal_code == ""
        assert cfg.address.prefecture == ""
        assert cfg.address.city == ""
        assert cfg.address.street == ""
        assert cfg.address.building == ""
        assert cfg.address.jan1_address is None

    def test_default_business_address_none(self):
        cfg = ShinkokuConfig()
        assert cfg.business_address is None

    def test_default_business_empty(self):
        cfg = ShinkokuConfig()
        assert cfg.business.trade_name == ""
        assert cfg.business.industry_type == ""
        assert cfg.business.business_description == ""
        assert cfg.business.establishment_year is None

    def test_default_filing(self):
        cfg = ShinkokuConfig()
        assert cfg.filing.submission_method == "e-tax"
        assert cfg.filing.return_type == "blue"
        assert cfg.filing.blue_return_deduction == 650_000
        assert cfg.filing.electronic_bookkeeping is False
        assert cfg.filing.tax_office_name == ""

    def test_default_directory_fields_none(self):
        cfg = ShinkokuConfig()
        assert cfg.invoice_registration_number is None
        assert cfg.invoices_dir is None
        assert cfg.withholding_slips_dir is None
        assert cfg.past_returns_dir is None
        assert cfg.deductions_dir is None
        assert cfg.receipts_dir is None
        assert cfg.bank_statements_dir is None
        assert cfg.credit_card_statements_dir is None
        assert cfg.furusato_receipts_dir is None

    def test_partial_config_uses_defaults(self, tmp_path):
        """一部セクションのみ記載した場合、省略セクションはデフォルトになる。"""
        config_file = tmp_path / "partial.yaml"
        config_file.write_text(
            "tax_year: 2024\ntaxpayer:\n  last_name: 佐藤\n",
            encoding="utf-8",
        )
        cfg = load_config(str(config_file))
        assert cfg.tax_year == 2024
        assert cfg.taxpayer.last_name == "佐藤"
        assert cfg.taxpayer.first_name == ""  # デフォルト
        assert cfg.address.prefecture == ""  # address セクション省略 -> デフォルト
        assert cfg.business.trade_name == ""  # business セクション省略 -> デフォルト
        assert cfg.filing.return_type == "blue"  # filing セクション省略 -> デフォルト


class TestMyNumber:
    """マイナンバーフィールドが正しく読み込まれることを確認。"""

    def test_my_number_loaded(self, full_config_yaml):
        cfg = load_config(str(full_config_yaml))
        assert cfg.taxpayer.my_number == "123456789012"

    def test_my_number_is_string(self, full_config_yaml):
        """マイナンバーは文字列型で保持される（先頭ゼロ対応）。"""
        cfg = load_config(str(full_config_yaml))
        assert isinstance(cfg.taxpayer.my_number, str)

    def test_my_number_none_when_omitted(self, minimal_config_yaml):
        cfg = load_config(str(minimal_config_yaml))
        assert cfg.taxpayer.my_number is None

    def test_my_number_with_leading_zero(self, tmp_path):
        """先頭ゼロのマイナンバーが文字列として正しく保持される。"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            'tax_year: 2025\ndb_path: ./test.db\ntaxpayer:\n  my_number: "012345678901"\n',
            encoding="utf-8",
        )
        cfg = load_config(str(config_file))
        assert cfg.taxpayer.my_number == "012345678901"
        assert cfg.taxpayer.my_number.startswith("0")


class TestEmptyConfigFile:
    """空の YAML ファイルでもデフォルト値で読み込めることを確認。"""

    def test_empty_yaml_loads_defaults(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("", encoding="utf-8")
        cfg = load_config(str(config_file))
        assert isinstance(cfg, ShinkokuConfig)
        assert cfg.tax_year == 2025
        assert cfg.db_path == "./shinkoku.db"


class TestDetermineBlueReturnDeduction:
    """青色申告特別控除額の自動判定ロジック（国税庁 No.2072）。"""

    def test_etax_without_electronic_bookkeeping(self):
        """e-Tax提出だけで65万円控除（電子帳簿保存は不問）。"""
        result = determine_blue_return_deduction(
            submission_method="e-tax",
            return_type="blue",
            electronic_bookkeeping=False,
            simple_bookkeeping=False,
        )
        assert result == 650_000

    def test_etax_with_electronic_bookkeeping(self):
        """e-Tax提出 + 電子帳簿保存でも65万円。"""
        result = determine_blue_return_deduction(
            submission_method="e-tax",
            return_type="blue",
            electronic_bookkeeping=True,
            simple_bookkeeping=False,
        )
        assert result == 650_000

    def test_mail_without_electronic_bookkeeping(self):
        """書面提出（郵送）+ 電子帳簿保存なし → 55万円。"""
        result = determine_blue_return_deduction(
            submission_method="mail",
            return_type="blue",
            electronic_bookkeeping=False,
            simple_bookkeeping=False,
        )
        assert result == 550_000

    def test_mail_with_electronic_bookkeeping(self):
        """書面提出（郵送）+ 電子帳簿保存あり → 65万円。"""
        result = determine_blue_return_deduction(
            submission_method="mail",
            return_type="blue",
            electronic_bookkeeping=True,
            simple_bookkeeping=False,
        )
        assert result == 650_000

    def test_in_person_without_electronic_bookkeeping(self):
        """書面提出（持参）+ 電子帳簿保存なし → 55万円。"""
        result = determine_blue_return_deduction(
            submission_method="in-person",
            return_type="blue",
            electronic_bookkeeping=False,
            simple_bookkeeping=False,
        )
        assert result == 550_000

    def test_in_person_with_electronic_bookkeeping(self):
        """書面提出（持参）+ 電子帳簿保存あり → 65万円。"""
        result = determine_blue_return_deduction(
            submission_method="in-person",
            return_type="blue",
            electronic_bookkeeping=True,
            simple_bookkeeping=False,
        )
        assert result == 650_000

    def test_simple_bookkeeping(self):
        """簡易帳簿 → 10万円（提出方法に関わらず）。"""
        result = determine_blue_return_deduction(
            submission_method="e-tax",
            return_type="blue",
            electronic_bookkeeping=False,
            simple_bookkeeping=True,
        )
        assert result == 100_000

    def test_white_return(self):
        """白色申告 → 0円（青色申告特別控除なし）。"""
        result = determine_blue_return_deduction(
            submission_method="e-tax",
            return_type="white",
            electronic_bookkeeping=False,
            simple_bookkeeping=False,
        )
        assert result == 0


class TestFilingConfigValidator:
    """FilingConfig の model_validator による控除額自動補正。"""

    def test_etax_blue_auto_sets_650000(self):
        """e-Tax + 複式簿記 → blue_return_deduction が 650,000 に自動設定される。"""
        filing = FilingConfig(
            submission_method="e-tax",
            return_type="blue",
            electronic_bookkeeping=False,
        )
        assert filing.blue_return_deduction == 650_000

    def test_mail_blue_auto_sets_550000(self):
        """郵送 + 複式簿記 + 電子帳簿保存なし → 550,000 に自動補正。"""
        filing = FilingConfig(
            submission_method="mail",
            return_type="blue",
            electronic_bookkeeping=False,
        )
        assert filing.blue_return_deduction == 550_000

    def test_mail_blue_with_bookkeeping_auto_sets_650000(self):
        """郵送 + 電子帳簿保存あり → 650,000 に自動補正。"""
        filing = FilingConfig(
            submission_method="mail",
            return_type="blue",
            electronic_bookkeeping=True,
        )
        assert filing.blue_return_deduction == 650_000

    def test_simple_bookkeeping_auto_sets_100000(self):
        """簡易帳簿 → 100,000 に自動補正。"""
        filing = FilingConfig(
            submission_method="e-tax",
            return_type="blue",
            simple_bookkeeping=True,
        )
        assert filing.blue_return_deduction == 100_000

    def test_overridden_deduction_gets_corrected(self):
        """手動で不整合な値を設定しても自動補正される。"""
        filing = FilingConfig(
            submission_method="mail",
            return_type="blue",
            electronic_bookkeeping=False,
            blue_return_deduction=650_000,  # 不正: 郵送+電子帳簿なしなら55万
        )
        assert filing.blue_return_deduction == 550_000
