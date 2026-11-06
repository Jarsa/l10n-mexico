# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import logging

from lxml import etree

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Read the payment complements already downloaded."""
    documents = env["l10n_mx_sat.document"].search(
        [("voucher_type", "=", "P"), ("has_xml", "=", True)]
    )
    for document in documents:
        try:
            document._l10n_mx_sat_payment_parse(
                etree.fromstring(
                    document.attachment_id.with_context(bin_size=False).raw
                )
            )
        except Exception as err:  # noqa: BLE001 - one bad XML must not stop the install
            _logger.warning("%s: payment complement not read: %s", document.uuid, err)
    _logger.info("%s payment complements read", len(documents))
