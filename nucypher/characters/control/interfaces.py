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

from base64 import b64decode
from typing import Union

import maya

from nucypher.characters.base import Character
from nucypher.characters.control.specifications import alice, bob, enrico
from nucypher.control.interfaces import attach_schema, ControlInterface
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.crypto.umbral_adapter import PublicKey
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.hrac import HRAC
from nucypher.policy.kits import MessageKit
from nucypher.policy.maps import EncryptedTreasureMap


class CharacterPublicInterface(ControlInterface):

    def __init__(self, character: Character = None, *args, **kwargs):
        super().__init__(implementer=character, *args, **kwargs)


class AliceInterface(CharacterPublicInterface):

    @attach_schema(alice.CreatePolicy)
    def create_policy(self,
                      bob_encrypting_key: bytes,
                      bob_verifying_key: bytes,
                      label: bytes,
                      threshold: int,
                      shares: int,
                      expiration: maya.MayaDT,
                      value: int = None
                      ) -> dict:

        from nucypher.characters.lawful import Bob
        bob = Bob.from_public_keys(encrypting_key=bob_encrypting_key,
                                   verifying_key=bob_verifying_key)

        new_policy = self.implementer.create_policy(
            bob=bob,
            label=label,
            threshold=threshold,
            shares=shares,
            expiration=expiration,
            value=value
        )
        response_data = {'label': new_policy.label, 'policy_encrypting_key': new_policy.public_key}
        return response_data

    @attach_schema(alice.DerivePolicyEncryptionKey)
    def derive_policy_encrypting_key(self, label: bytes) -> dict:
        policy_encrypting_key = self.implementer.get_policy_encrypting_key_from_label(label)
        response_data = {'policy_encrypting_key': policy_encrypting_key, 'label': label}
        return response_data

    @attach_schema(alice.GrantPolicy)
    def grant(self,
              bob_encrypting_key: bytes,
              bob_verifying_key: bytes,
              label: bytes,
              threshold: int,
              shares: int,
              expiration: maya.MayaDT,
              value: int = None,
              rate: int = None,
              ) -> dict:

        from nucypher.characters.lawful import Bob
        bob = Bob.from_public_keys(encrypting_key=bob_encrypting_key,
                                   verifying_key=bob_verifying_key)

        new_policy = self.implementer.grant(bob=bob,
                                            label=label,
                                            threshold=threshold,
                                            shares=shares,
                                            value=value,
                                            rate=rate,
                                            expiration=expiration)

        response_data = {'treasure_map': new_policy.treasure_map,
                         'policy_encrypting_key': new_policy.public_key,
                         # For the users of this interface, Publisher is always the same as Alice,
                         # so we are only returning the Alice's key.
                         'alice_verifying_key': self.implementer.stamp.as_umbral_pubkey()}

        return response_data

    @attach_schema(alice.Revoke)
    def revoke(self, label: bytes, bob_verifying_key: bytes) -> dict:

        # TODO: Move deeper into characters
        policy_hrac = HRAC.derive(self.implementer.stamp.as_umbral_pubkey(), bob_verifying_key, label)
        policy = self.implementer.active_policies[policy_hrac]

        receipt, failed_revocations = self.implementer.revoke(policy)
        if len(failed_revocations) > 0:
            for node_id, attempt in failed_revocations.items():
                revocation, fail_reason = attempt
                if fail_reason == RestMiddleware.NotFound:
                    del (failed_revocations[node_id])
        if len(failed_revocations) <= (policy.shares - policy.threshold + 1):
            del (self.implementer.active_policies[policy_hrac])

        response_data = {'failed_revocations': len(failed_revocations)}
        return response_data

    @attach_schema(alice.Decrypt)
    def decrypt(self, label: bytes, message_kit: bytes) -> dict:
        """
        Character control endpoint to allow Alice to decrypt her own data.
        """

        from nucypher.characters.lawful import Enrico
        policy_encrypting_key = self.implementer.get_policy_encrypting_key_from_label(label)

        # TODO #846: May raise UnknownOpenSSLError and InvalidTag.
        message_kit = MessageKit.from_bytes(message_kit)

        enrico = Enrico.from_public_keys(
            verifying_key=message_kit.sender_verifying_key,
            policy_encrypting_key=policy_encrypting_key,
            label=label
        )

        plaintexts = self.implementer.decrypt_message_kit(
            message_kit=message_kit,
            data_source=enrico,
            label=label
        )

        response = {'cleartexts': plaintexts}
        return response

    @attach_schema(alice.PublicKeys)
    def public_keys(self) -> dict:
        """
        Character control endpoint for getting Alice's public keys.
        """
        verifying_key = self.implementer.public_keys(SigningPower)
        response_data = {'alice_verifying_key': verifying_key}
        return response_data


class BobInterface(CharacterPublicInterface):

    @attach_schema(bob.RetrieveAndDecrypt)
    def retrieve_and_decrypt(self,
                             policy_encrypting_key: bytes,
                             alice_verifying_key: bytes,
                             message_kit: bytes,
                             encrypted_treasure_map: Union[bytes, str, 'EncryptedTreasureMap']):
        """
        Character control endpoint for re-encrypting and decrypting policy data.
        """
        from nucypher.characters.lawful import Enrico

        policy_encrypting_key = PublicKey.from_bytes(policy_encrypting_key)
        alice_verifying_key = PublicKey.from_bytes(alice_verifying_key)
        message_kit = MessageKit.from_bytes(message_kit)  # TODO #846: May raise UnknownOpenSSLError and InvalidTag.

        if isinstance(encrypted_treasure_map, bytes):
            encrypted_treasure_map = EncryptedTreasureMap.from_bytes(encrypted_treasure_map)

        if isinstance(encrypted_treasure_map, str):
            tmap_bytes = encrypted_treasure_map.encode()
            encrypted_treasure_map = EncryptedTreasureMap.from_bytes(b64decode(tmap_bytes))

        plaintexts = self.implementer.retrieve_and_decrypt([message_kit],
                                                           policy_encrypting_key=policy_encrypting_key,
                                                           alice_verifying_key=alice_verifying_key,
                                                           encrypted_treasure_map=encrypted_treasure_map)

        response_data = {'cleartexts': plaintexts}
        return response_data

    @attach_schema(bob.PublicKeys)
    def public_keys(self):
        """
        Character control endpoint for getting Bob's encrypting and signing public keys
        """
        verifying_key = self.implementer.public_keys(SigningPower)
        encrypting_key = self.implementer.public_keys(DecryptingPower)
        response_data = {'bob_encrypting_key': encrypting_key, 'bob_verifying_key': verifying_key}
        return response_data


class EnricoInterface(CharacterPublicInterface):

    @attach_schema(enrico.EncryptMessage)
    def encrypt_message(self, plaintext: Union[str, bytes]):
        """
        Character control endpoint for encrypting data for a policy and
        receiving the messagekit (and signature) to give to Bob.
        """
        message_kit = self.implementer.encrypt_message(plaintext=plaintext)
        response_data = {'message_kit': message_kit}
        return response_data
