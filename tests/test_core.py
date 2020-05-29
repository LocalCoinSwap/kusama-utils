import copy

import pytest

from . import mocked_returns
from ksmutils import Kusama


class TestVersionEndpoint:
    def test_version_check(self, network):
        kusama = Kusama()
        kusama.connect(network=network)


class TestNoNetwork:
    def test_connect_no_network(self, mocker):
        mocker.patch("ksmutils.network.Network.__init__", return_value=None)
        mocker.patch("ksmutils.core.Kusama.check_version", return_value=1062)
        mocker.patch("ksmutils.core.Kusama.get_metadata")
        mocker.patch("ksmutils.core.Kusama.get_spec_version")
        mocker.patch("ksmutils.core.Kusama.get_genesis_hash")
        kusama = Kusama()
        kusama.connect()


class TestGetMethods:
    def test_get_balance(self, network):
        kusama = Kusama()
        kusama.connect(network=network)

        result = kusama.get_balance("HsgNgA5sgjuKxGUeaZPJE8rRn9RuixjvnPkVLFUYLEpj15G")

        assert result == 22000000000

    def test_get_nonce(self, network):
        kusama = Kusama()
        kusama.connect(network=network)

        result = kusama.get_nonce("HsgNgA5sgjuKxGUeaZPJE8rRn9RuixjvnPkVLFUYLEpj15G")

        assert result == 0

    def test_get_escrow_address(self, network):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        buyer_address = "DwRh5ShcnuPzgyhW6J6m4mw1y63hUy1ctR3RSWRSgLg1HQ5"
        seller_address = "CrjrfWVeFM7CFc3fvhwA7etuTdGirnSqBBNBzTiyTcRrPsP"

        result = kusama.get_escrow_address(buyer_address, seller_address)

        assert result == "Fgh5GQ1guNxvurv71cmHm8H5Eo8Ywrdz1mZemffAP2UrrH2"

    def test_get_block(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        block_hash = (
            "0xa8495cdf2eaf0025966e96b06fba92f647e1e316f2abc698186ecf67919dc52b"
        )

        mocker.patch(
            "ksmutils.network.Network.node_rpc_call",
            return_value=mocked_returns.node_rpc_call_return_2,
        )

        result = kusama.get_block(block_hash)

        expected_number = 2493157
        assert result.get("block").get("header").get("number") == expected_number

    def test_get_events(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        block_hash = (
            "0xa8495cdf2eaf0025966e96b06fba92f647e1e316f2abc698186ecf67919dc52b"
        )

        mocker.patch(
            "ksmutils.network.Network.node_rpc_call",
            return_value=mocked_returns.node_rpc_call_return_1,
        )

        result = kusama.get_events(block_hash)

        assert len(result) > 0

    def test_get_extrinsic_events(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        block_hash = (
            "0xa8495cdf2eaf0025966e96b06fba92f647e1e316f2abc698186ecf67919dc52b"
        )
        extrinsic_index = 3

        mocker.patch(
            "ksmutils.core.Kusama.get_events",
            return_value=mocked_returns.get_events_return_1,
        )

        result = kusama.get_extrinsic_events(block_hash, extrinsic_index)
        assert len(result) > 0

        for event in result:
            assert event["extrinsic_idx"] == extrinsic_index

    def test_get_extrinsic_timepoint(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        node_response = {
            0: {"jsonrpc": "2.0", "result": 723219, "id": 1},
            1: {
                "jsonrpc": "2.0",
                "method": "author_extrinsicUpdate",
                "params": {
                    "result": {
                        "finalized": "0xa8495cdf2eaf0025966e96b06fba92f647e1e316f2abc698186ecf67919dc52b"
                    },
                    "subscription": 723219,
                },
            },
        }

        extrinsic_data = (
            "0x35028444ac0e6cb2c7e9adfcc86919959ff044cd6f6aefcc99152592a4fe8e6d22ce7"
            "701d86d7a5e2fdecb5a927a2e38beb91ec2d7ac97680d8271638676684c3d1f0e5fec54"
            "215035204e2e0d6323e029cee37938c5984bdca37d1c1fa7890cdecd7a8200b0000400b"
            "e51e7d8eb439683272967dfce076362514e8519a51164e73f21272d157b446e0700e40b5402"
        )

        get_block_return_value = copy.deepcopy(mocked_returns.get_block_mock_1)

        mocker.patch(
            "ksmutils.core.Kusama.get_block", return_value=get_block_return_value
        )

        expected_result = (2493157, 3)
        result = kusama.get_extrinsic_timepoint(node_response, extrinsic_data)
        assert result == expected_result

    def test_get_extrinsic_timepoint_exception_1(self, network):
        kusama = Kusama()
        kusama.connect(network=network)

        with pytest.raises(Exception) as excinfo:
            kusama.get_extrinsic_timepoint({}, "")
        assert "node_response is empty" in str(excinfo.value)

    def test_get_extrinsic_timepoint_exception_2(self, network):
        kusama = Kusama()
        kusama.connect(network=network)

        node_response = {0: {"jsonrpc": "2.0", "result": 723219, "id": 1}}

        with pytest.raises(Exception) as excinfo:
            kusama.get_extrinsic_timepoint(node_response, "")
        assert "Last item in the node_response is not finalized hash" in str(
            excinfo.value
        )

    def test__get_extrinsix_index(self, network):
        kusama = Kusama()
        kusama.connect(network=network)

        assert kusama._get_extrinsix_index([], "") == -1

    def test_escrow_payloads(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)
        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=46)
        # seller_address, escrow_address, trade_value, fee_value

    def test_cancellation(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)
        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=46)
        # seller_address, trade_value, fee_value, other_signatories

    def test_resolve_dispute(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)
        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=46)
        # victor, seller_address, trade_value, fee_value, other_signatories


class TestNonceManager:
    def test_arbitrator_nonce(self, network, mocker):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=2)
        result = kusama.arbitrator_nonce()

        assert result == 2


class TestWrapperMethods:
    # These tests aren't really necessary because they just call another
    # function which are already testd,
    # a better way would be to test if that other function
    # gets called ONCE, can't figure out how to do this without unittest
    def test_broadcast(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        mocker.patch("ksmutils.network.Network.node_rpc_call")

        mocker.patch("ksmutils.core.Kusama.get_extrinsic_hash", return_value="a")
        mocker.patch("ksmutils.core.Kusama.get_block_hash")
        mocker.patch(
            "ksmutils.core.Kusama.get_extrinsic_timepoint", return_value=(1, 2)
        )
        mocker.patch("ksmutils.core.Kusama.get_extrinsic_events", return_value=[])
        mocker.patch("ksmutils.core.Kusama.is_transaction_success", return_value=True)

        result = kusama.broadcast("t", "tx")
        assert result == ("a", (1, 2), True)

    def test_publish(self, network, mocker):
        kusama = Kusama()
        arbitrator_key = (
            "b5643fe4084cae15ffbbc5c1cbe734bec5da9c351f4aa4d44f2897efeb8375c8"
        )
        kusama.setup_arbitrator(arbitrator_key)
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.broadcast", return_value=True)
        mocker.patch("ksmutils.helper.unsigned_transfer_construction")
        mocker.patch("ksmutils.helper.unsigned_transfer_construction")
        mocker.patch("ksmutils.helper.unsigned_approve_as_multi_construction")
        mocker.patch("ksmutils.helper.unsigned_as_multi_construction")

        assert kusama.publish("transfer", [True])
        assert kusama.publish("fee_transfer", [1, 2, 3, 4])
        assert kusama.publish("approve_as_multi", [1, 2, 3, 4])
        assert kusama.publish("as_multi", [1, 2, 3, 4])

    def test_is_transaction_success(self, network):
        kusama = Kusama()
        kusama.connect(network=network)
        assert kusama.is_transaction_success("transfer", [{"event_id": "Transfer"}])

    def test_transfer_payload(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=4)
        mocker.patch("ksmutils.helper.transfer_signature_payload", return_value=None)

        assert kusama.transfer_payload("", "", 0) is None

    def test_approve_as_multi_payload(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=4)
        mocker.patch(
            "ksmutils.helper.approve_as_multi_signature_payload", return_value=None
        )

        assert kusama.approve_as_multi_payload("", "", 0, []) == (None, 4)

    def test_as_multi_payload(self, network, mocker):
        kusama = Kusama()
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.get_nonce", return_value=4)
        mocker.patch("ksmutils.helper.as_multi_signature_payload", return_value=None)

        assert kusama.as_multi_payload("", "", 0, []) == (None, 4)

    def test_release_escrow(self, network, mocker):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.arbitrator_nonce", return_value=4)
        mocker.patch("ksmutils.helper.as_multi_signature_payload", return_value=None)
        mocker.patch("ksmutils.helper.sign_payload", return_value=None)
        mocker.patch(
            "ksmutils.helper.unsigned_as_multi_construction", return_value="tx"
        )

        assert kusama.release_escrow("", "", (1, 2), []) == "tx"

    def test_cancellation(self, network, mocker):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.arbitrator_nonce", return_value=4)
        mocker.patch("ksmutils.helper.as_multi_signature_payload", return_value=None)
        mocker.patch("ksmutils.helper.transfer_signature_payload", return_value=None)
        mocker.patch("ksmutils.helper.sign_payload", return_value=None)
        mocker.patch(
            "ksmutils.helper.unsigned_as_multi_construction", return_value="tx"
        )
        mocker.patch(
            "ksmutils.helper.unsigned_transfer_construction", return_value="fx"
        )
        assert kusama.cancellation("", 1, 0.01, [], (1, 2)) == ("tx", "fx")

        with pytest.raises(Exception) as excinfo:
            kusama.cancellation("", 1, 0.02, [], (1, 2)) == ("tx", "fx")
        assert "Fee should not be more than 1% of trade value" in str(excinfo.value)

    def test_resolve_dispute_seller_wins(self, network, mocker):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.arbitrator_nonce", return_value=4)

        mocker.patch("ksmutils.core.Kusama.cancellation", return_value=("tx", "fx"))

        assert kusama.resolve_dispute("seller", "", 1, 0.01, []) == ("tx", "fx")

    def test_resolve_dispute_buyer_wins(self, network, mocker):
        kusama = Kusama(
            arbitrator_key="5c65b9f9f75f95d70b84577ab07e22f7400d394ca3c8bcb227fb6d42920d9b50"
        )
        kusama.connect(network=network)

        mocker.patch("ksmutils.core.Kusama.arbitrator_nonce", return_value=4)
        mocker.patch(
            "ksmutils.helper.approve_as_multi_signature_payload", return_value=None
        )
        mocker.patch("ksmutils.helper.transfer_signature_payload", return_value=None)
        mocker.patch("ksmutils.helper.sign_payload", return_value=None)
        mocker.patch(
            "ksmutils.helper.unsigned_approve_as_multi_construction", return_value="tx"
        )
        mocker.patch(
            "ksmutils.helper.unsigned_transfer_construction", return_value="wx"
        )

        assert kusama.resolve_dispute("buyer", "", 1, 0.01, []) == ("tx", "wx")
