"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from typing import Optional

from bytestring_splitter import BytestringSplitter
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_canonical_address, to_checksum_address

from nucypher.crypto.signing import SignatureStamp, InvalidSignature
from nucypher.crypto.splitters import signature_splitter, checksum_address_splitter
from nucypher.crypto.umbral_adapter import Signature, PublicKey
from nucypher.policy.kits import MessageKit
from nucypher.policy.maps import AuthorizedKeyFrag


class Revocation:
    """
    Represents a string used by characters to perform a revocation on a specific
    Ursula. It's a bytestring made of the following format:
    REVOKE-<arrangement id to revoke><signature of the previous string>
    This is sent as a payload in a DELETE method to the /KFrag/ endpoint.
    """

    PREFIX = b'REVOKE-'
    revocation_splitter = BytestringSplitter(
        (bytes, len(PREFIX)),
        checksum_address_splitter, # ursula canonical address
        (bytes, AuthorizedKeyFrag.ENCRYPTED_SIZE),  # encrypted kfrag payload (includes writ)
        signature_splitter
    )

    def __init__(self,
                 ursula_checksum_address: ChecksumAddress,  # TODO: Use staker address instead (what if the staker rebonds)?
                 encrypted_kfrag: MessageKit,
                 signer: Optional[SignatureStamp] = None,
                 signature: Optional[Signature] = None):

        self.ursula_checksum_address = ursula_checksum_address
        self.encrypted_kfrag = encrypted_kfrag

        if not (bool(signer) ^ bool(signature)):
            raise ValueError("Either pass a signer or a signature; not both.")
        elif signer:
            self.signature = signer(self.payload)
        elif signature:
            self.signature = signature

    def __bytes__(self):
        return self.payload + bytes(self.signature)

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @property
    def payload(self):
        return self.PREFIX                                          \
               + to_canonical_address(self.ursula_checksum_address) \
               + bytes(self.encrypted_kfrag)                        \

    @classmethod
    def from_bytes(cls, revocation_bytes):
        prefix, ursula_canonical_address, ekfrag, signature = cls.revocation_splitter(revocation_bytes)
        ursula_checksum_address = to_checksum_address(ursula_canonical_address)
        return cls(ursula_checksum_address=ursula_checksum_address,
                   encrypted_kfrag=ekfrag,
                   signature=signature)

    def verify_signature(self, alice_verifying_key: PublicKey) -> bool:
        """
        Verifies the revocation was from the provided pubkey.
        """
        if not self.signature.verify(self.payload, alice_verifying_key):
            raise InvalidSignature(f"Revocation has an invalid signature: {self.signature}")
        return True


class RevocationKit:

    def __init__(self, treasure_map, signer: SignatureStamp):
        self.revocations = dict()
        for node_id, encrypted_kfrag in treasure_map:
            self.revocations[node_id] = Revocation(ursula_checksum_address=node_id,
                                                   encrypted_kfrag=encrypted_kfrag,
                                                   signer=signer)

    def __iter__(self):
        return iter(self.revocations.values())

    def __getitem__(self, node_id):
        return self.revocations[node_id]

    def __len__(self):
        return len(self.revocations)

    def __eq__(self, other):
        return self.revocations == other.revocations

    @property
    def revokable_addresses(self):
        """
        Returns a Set of revokable addresses in the checksum address formatting
        """
        return set(self.revocations.keys())

    def add_confirmation(self, node_id, signed_receipt):
        """
        Adds a signed confirmation of Ursula's ability to revoke the arrangement.
        """
        # TODO: Verify Ursula's signature
        # TODO: Implement receipts
        raise NotImplementedError
