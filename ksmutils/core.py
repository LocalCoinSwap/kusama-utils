import asyncio
import json
import logging
from hashlib import blake2b

import sr25519
import websockets
from scalecodec import ScaleBytes
from scalecodec.base import RuntimeConfiguration
from scalecodec.base import ScaleDecoder
from scalecodec.block import ExtrinsicsDecoder
from scalecodec.metadata import MetadataDecoder
from scalecodec.type_registry import load_type_registry_preset
from scalecodec.utils.ss58 import ss58_decode
from scalecodec.utils.ss58 import ss58_encode

from .helper import approve_as_multi_signature_payload
from .helper import transfer_call_and_signature_payload
from .network import Network

# Hardcode this because we WANT things to break if it changes
BLOCKCHAIN_VERSION = 1062

logger = logging.getLogger(__name__)


class Kusama:
    def __init__(
        self,
        *,
        node_url: str = "wss://kusama-rpc.polkadot.io/",
        arbitrator_key: str = None,
    ):
        self.node_url = node_url
        if arbitrator_key:
            self.setup_arbitrator(arbitrator_key)

    def connect(self, *, node_url: str = "", network: "Network" = None):
        node_url = self.node_url if not node_url else node_url
        if not network:
            network = Network(node_url=node_url)

        self.network = network
        assert self.check_version() == BLOCKCHAIN_VERSION

        RuntimeConfiguration().update_type_registry(
            load_type_registry_preset("default")
        )
        RuntimeConfiguration().update_type_registry(load_type_registry_preset("kusama"))

        self.metadata = self.get_metadata()
        self.spec_version = self.get_spec_version()
        self.genesis_hash = self.get_genesis_hash()

    def setup_arbitrator(self, arbitrator_key):
        self.keypair = sr25519.pair_from_seed(bytes.fromhex(arbitrator_key))
        self.arbitrator_account_id = self.keypair[0].hex()
        self.arbitrator_address = ss58_encode(self.keypair[0], 2)

    def check_version(self):
        """
        Make sure the versioning of the Kusama blockchain has not been
        updated since the last developer verification of the codebase
        """
        version = self.network.node_rpc_call(
            "state_getRuntimeVersion", [], loop_limit=1
        )
        return version[0]["result"]["specVersion"]

    def get_metadata(self):
        raw_metadata = self.network.node_rpc_call(
            "state_getMetadata", [None], loop_limit=1
        )[0]["result"]
        metadata = MetadataDecoder(ScaleBytes(raw_metadata))
        metadata.decode()
        return metadata

    def get_spec_version(self):
        return BLOCKCHAIN_VERSION

    def get_genesis_hash(self):
        return self.network.node_rpc_call("chain_getBlockHash", [0], loop_limit=1)[0][
            "result"
        ]

    def _get_address_info(self, address):
        # xxHash128(System) + xxHash128(Account)
        storage_key = (
            "0x26aa394eea5630e07c48ae0c9558cef7b99d880ec681799c0cf30e8886371da9"
        )

        account_id = ss58_decode(address, 2)
        hashed_address = f"{blake2b(bytes.fromhex(account_id), digest_size=16).digest().hex()}{account_id}"
        storage_hash = storage_key + hashed_address

        result = self.network.node_rpc_call(
            "state_getStorageAt", [storage_hash, None], loop_limit=1
        )[0]["result"]

        return_decoder = ScaleDecoder.get_decoder_class(
            "AccountInfo<Index, AccountData>",
            ScaleBytes(result),
            metadata=self.metadata,
        )
        return return_decoder.decode()

    def get_balance(self, address):
        result = self._get_address_info(address)
        return result["data"]["free"]

    def get_nonce(self, address):
        result = self._get_address_info(address)
        return result["nonce"]

    def get_block(self, block_hash):
        # FIXME: Modify node_rpc_call to return single item when there's only one
        response = self.network.node_rpc_call(
            "chain_getBlock", [block_hash], loop_limit=1
        )[0]["result"]

        response["block"]["header"]["number"] = int(
            response["block"]["header"]["number"], 16
        )

        for idx, data in enumerate(response["block"]["extrinsics"]):
            extrinsic_decoder = ExtrinsicsDecoder(
                data=ScaleBytes(data), metadata=self.metadata
            )
            extrinsic_decoder.decode()
            response["block"]["extrinsics"][idx] = extrinsic_decoder.value

        return response

    def _get_extrinsix_index(self, block_extrinsics, extrinsic_hash):
        for idx, extrinsics in enumerate(block_extrinsics):
            ehash = extrinsics.get("extrinsic_hash")
            if ehash == extrinsic_hash:
                return idx
        return 0

    def get_extrinsic_timepoint(self, node_response, extrinsic_data):
        if not node_response:
            raise Exception("node_response is empty")

        last_item = node_response[len(node_response) - 1]
        finalized_hash = last_item.get("params", {}).get("result", {}).get("finalized")

        if not finalized_hash:
            raise Exception("Last item in the node_response is not finalized hash")

        extrinsic_hash = (
            blake2b(bytes.fromhex(extrinsic_data[2:]), digest_size=32).digest().hex()
        )

        block = self.get_block(finalized_hash)
        block_number = block.get("block").get("header").get("number")
        extrinsic_index = self._get_extrinsix_index(
            block.get("block").get("extrinsics"), extrinsic_hash
        )

        return (block_number, extrinsic_index)

    def broadcast_extrinsic(self, extrinsic_data, request_id=1, loop_forever=False):
        """
        Raw extrinsic broadcast
        """

        payload = {
            "jsonrpc": "2.0",
            "method": "author_submitAndWatchExtrinsic",
            "params": [str(extrinsic_data)],
            "id": request_id,
        }
        ws_results = {}

        async def ws_request(payload):
            async with websockets.connect(self.node_url) as websocket:
                await websocket.send(json.dumps(payload))
                event_number = 0
                looping = True
                while looping:
                    result = json.loads(await websocket.recv())
                    ws_results.update({event_number: result})

                    # This is nasty but nested ifs are worse
                    if (
                        "params" in result
                        and type(result["params"]["result"]) is dict
                        and "finalized" in result["params"]["result"]
                    ):
                        looping = False
                        looping = loop_forever

                    event_number += 1

        asyncio.run(ws_request(payload))
        return ws_results

    def broadcast(self, sender_address, signature, call_info, nonce):
        """
        Handles final transaction construction according to transaction type
        """
        sender_account_id = "0x{}".format(ss58_decode(sender_address, 2))
        signature = "0x{}".format(signature.hex())
        # Create extrinsic
        extrinsic = ScaleDecoder.get_decoder_class("Extrinsic", metadata=self.metadata)
        extrinsic.encode(
            {
                "account_id": sender_account_id,
                "signature_version": 1,
                "signature": signature,
                "call_function": call_info.value["call_function"],
                "call_module": call_info.value["call_module"],
                "call_args": call_info.value["call_args"],
                "nonce": nonce,
                "era": "00",
                "tip": 0,
            }
        )
        return extrinsic

    def transfer_payload(self, from_address, to_address, value):
        """
        Get signature payloads and call data for a regular transfer
        """
        nonce = self.get_nonce(from_address)
        return transfer_call_and_signature_payload(
            self.metadata,
            to_address,
            value,
            nonce,
            self.genesis_hash,
            self.spec_version,
        )

    def escrow_payloads(self, seller_address, escrow_address, trade_value, fee_value):
        """
        Get signature payloads and call data for funding the multisig escrow,
        and sending the fee to the arbitrator
        """
        nonce = self.get_nonce(seller_address)
        escrow_extrinsic_info = transfer_call_and_signature_payload(
            self.metadata,
            escrow_address,
            trade_value,
            nonce,
            self.genesis_hash,
            self.spec_version,
        )
        fee_extrinsic_info = transfer_call_and_signature_payload(
            self.metadata,
            self.arbitrator_address,
            fee_value,
            nonce + 1,
            self.genesis_hash,
            self.spec_version,
        )
        return escrow_extrinsic_info, fee_extrinsic_info

    def cancellation(self, seller_address, trade_value, fee_value, other_signatories):
        """
        1. Broadcast approveAsMulti from arbitrator to seller
        2. Verify that the asMulti passed successfully and that the fee is valid
        2. Broadcast fee return transfer from arbitrator to seller
        """
        assert fee_value <= trade_value * 0.01
        nonce = self.get_nonce(self.arbitrator_address)

        revert_payload = approve_as_multi_signature_payload(
            self.metadata,
            self.spec_version,
            self.genesis_hash,
            nonce,
            seller_address,
            trade_value,
            other_signatories,
        )
        fee_revert_payload = transfer_call_and_signature_payload(
            self.metadata,
            seller_address,
            fee_value,
            nonce + 1,
            self.genesis_hash,
            self.spec_version,
        )
        # TODO: Sign and publish transactions
        return revert_payload, fee_revert_payload

    def resolve_dispute(self):
        """
        1. If sellers wins then use cancellation flow
        2. If buyer wins then send broadcast approveAsMulti before
          sending funds to buyer
        """
        pass

    def get_escrow_address(self, buyer_address, seller_address, threshold=2):
        """
        Returns an escrow address for multisignature transactions
        """
        MultiAccountId = RuntimeConfiguration().get_decoder_class("MultiAccountId")

        multi_sig_account_id = MultiAccountId.create_from_account_list(
            [buyer_address, seller_address, self.arbitrator_address], 2
        )

        multi_sig_address = ss58_encode(multi_sig_account_id.value.replace("0x", ""), 2)
        return multi_sig_address
