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


import json
from base64 import b64decode, b64encode

import datetime
import maya
import pytest
from click.testing import CliRunner

import nucypher
from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.kits import MessageKit
from nucypher.policy.maps import EncryptedTreasureMap

click_runner = CliRunner()


def test_label_whose_b64_representation_is_invalid_utf8(alice_web_controller_test_client, create_policy_control_request):
    # In our Discord, user robin#2324 (github username @robin-thomas) reported certain labels
    # break Bob's retrieve endpoint.
    # convo starts here: https://ptb.discordapp.com/channels/411401661714792449/411401661714792451/564353305887637517

    bad_label = '516d593559505355376d454b61374751577146467a47754658396d516a685674716b7663744b376b4b666a35336d'

    method_name, params = create_policy_control_request
    params['label'] = bad_label

    # This previously caused an unhandled UnicodeDecodeError.  #920
    response = alice_web_controller_test_client.put(f'/{method_name}', data=json.dumps(params))
    assert response.status_code == 200


def test_alice_web_character_control_create_policy(alice_web_controller_test_client, create_policy_control_request):
    method_name, params = create_policy_control_request

    response = alice_web_controller_test_client.put(f'/{method_name}', data=json.dumps(params))
    assert response.status_code == 200

    create_policy_response = json.loads(response.data)
    assert 'version' in create_policy_response
    assert 'label' in create_policy_response['result']

    try:
        bytes.fromhex(create_policy_response['result']['policy_encrypting_key'])
    except (KeyError, ValueError):
        pytest.fail("Invalid Policy Encrypting Key")

    # Send bad data to assert error returns
    response = alice_web_controller_test_client.put('/create_policy', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400


def test_alice_web_character_control_derive_policy_encrypting_key(alice_web_controller_test_client):
    label = 'test'
    response = alice_web_controller_test_client.post(f'/derive_policy_encrypting_key/{label}')
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'policy_encrypting_key' in response_data['result']


def test_alice_web_character_control_grant(alice_web_controller_test_client, grant_control_request):
    method_name, params = grant_control_request
    endpoint = f'/{method_name}'

    response = alice_web_controller_test_client.put(endpoint, data=json.dumps(params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'treasure_map' in response_data['result']
    assert 'policy_encrypting_key' in response_data['result']
    assert 'alice_verifying_key' in response_data['result']

    map_bytes = b64decode(response_data['result']['treasure_map'])
    encrypted_map = EncryptedTreasureMap.from_bytes(map_bytes)
    assert encrypted_map.hrac is not None

    # Send bad data to assert error returns
    response = alice_web_controller_test_client.put(endpoint, data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    # Malform the request
    del(params['bob_encrypting_key'])
    response = alice_web_controller_test_client.put(endpoint, data=json.dumps(params))
    assert response.status_code == 400

    # test key validation with a bad key
    params['bob_encrypting_key'] = '12345'
    response = alice_web_controller_test_client.put(endpoint, data=json.dumps(params))
    assert response.status_code == 400
    assert b'non-hexadecimal number found in fromhex' in response.data


def test_alice_character_control_revoke(alice_web_controller_test_client, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    grant_request_data = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'label': 'test-revoke',
        'threshold': 2,
        'shares': 3,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
    }
    response = alice_web_controller_test_client.put('/grant', data=json.dumps(grant_request_data))
    assert response.status_code == 200

    revoke_request_data = {
        'label': 'test',
        'bob_verifying_key': bytes(federated_bob.stamp).hex()
    }

    response = alice_web_controller_test_client.delete(f'/revoke', data=json.dumps(revoke_request_data))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'result' in response_data
    assert 'failed_revocations' in response_data['result']
    assert response_data['result']['failed_revocations'] == 0


def test_alice_character_control_decrypt(alice_web_controller_test_client,
                                         enacted_federated_policy,
                                         capsule_side_channel):

    message_kit = capsule_side_channel()

    label = enacted_federated_policy.label.decode()
    policy_encrypting_key = bytes(enacted_federated_policy.public_key).hex()
    message_kit = b64encode(bytes(message_kit)).decode()

    request_data = {
        'label': label,
        'message_kit': message_kit,
    }

    response = alice_web_controller_test_client.post('/decrypt', data=json.dumps(request_data))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'cleartexts' in response_data['result']

    response_message = response_data['result']['cleartexts'][0]
    assert response_message == 'Welcome to flippering number 1.'  # This is the first message - in a test below, we'll show retrieving a second one.

    # Send bad data to assert error returns
    response = alice_web_controller_test_client.post('/decrypt', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    del(request_data['message_kit'])
    response = alice_web_controller_test_client.put('/decrypt', data=json.dumps(request_data))
    assert response.status_code == 405


def test_bob_web_character_control_retrieve(bob_web_controller_test_client, retrieve_control_request):
    method_name, params = retrieve_control_request
    endpoint = f'/{method_name}'

    response = bob_web_controller_test_client.post(endpoint, data=json.dumps(params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'cleartexts' in response_data['result']

    response_message = response_data['result']['cleartexts'][0]
    assert response_message == 'Welcome to flippering number 2.'  # This is the second message - the first is in the test above.

    # Send bad data to assert error returns
    response = bob_web_controller_test_client.post(endpoint, data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400


def test_bob_web_character_control_retrieve_again(bob_web_controller_test_client, retrieve_control_request):
    method_name, params = retrieve_control_request
    endpoint = f'/{method_name}'

    response = bob_web_controller_test_client.post(endpoint, data=json.dumps(params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'cleartexts' in response_data['result']

    response_message = response_data['result']['cleartexts'][0]
    assert response_message == 'Welcome to flippering number 2.'  # We have received exactly the same message again.

    del(params['alice_verifying_key'])
    response = bob_web_controller_test_client.post(endpoint, data=json.dumps(params))
    assert response.status_code == 400


def test_enrico_web_character_control_encrypt_message(enrico_web_controller_test_client, encrypt_control_request):
    method_name, params = encrypt_control_request
    endpoint = f'/{method_name}'
    response = enrico_web_controller_test_client.post(endpoint, data=json.dumps(params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'message_kit' in response_data['result']

    # Check that it serializes correctly.
    MessageKit.from_bytes(b64decode(response_data['result']['message_kit']))

    # Send bad data to assert error return
    response = enrico_web_controller_test_client.post('/encrypt_message', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    del(params['message'])
    response = enrico_web_controller_test_client.post('/encrypt_message', data=params)
    assert response.status_code == 400


def test_web_character_control_lifecycle(alice_web_controller_test_client,
                                         bob_web_controller_test_client,
                                         enrico_web_controller_from_alice,
                                         federated_alice,
                                         federated_bob,
                                         federated_ursulas,
                                         random_policy_label):

    random_label = random_policy_label.decode()  # Unicode string

    bob_keys_response = bob_web_controller_test_client.get('/public_keys')
    assert bob_keys_response.status_code == 200

    response_data = json.loads(bob_keys_response.data)
    assert str(nucypher.__version__) == response_data['version']
    bob_keys = response_data['result']
    assert 'bob_encrypting_key' in bob_keys
    assert 'bob_verifying_key' in bob_keys

    bob_encrypting_key_hex = bob_keys['bob_encrypting_key']
    bob_verifying_key_hex = bob_keys['bob_verifying_key']

    # Create a policy via Alice control
    alice_request_data = {
        'bob_encrypting_key': bob_encrypting_key_hex,
        'bob_verifying_key': bob_verifying_key_hex,
        'threshold': 1,
        'shares': 1,
        'label': random_label,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),  # TODO
    }

    response = alice_web_controller_test_client.put('/grant', data=json.dumps(alice_request_data))
    assert response.status_code == 200

    # Check Response Keys
    alice_response_data = json.loads(response.data)
    assert 'treasure_map' in alice_response_data['result']
    assert 'policy_encrypting_key' in alice_response_data['result']
    assert 'alice_verifying_key' in alice_response_data['result']
    assert 'version' in alice_response_data
    assert str(nucypher.__version__) == alice_response_data['version']

    # This is sidechannel policy metadata. It should be given to Bob by the
    # application developer at some point.
    policy_pubkey_enc_hex = alice_response_data['result']['policy_encrypting_key']
    alice_verifying_key_hex = alice_response_data['result']['alice_verifying_key']

    # Encrypt some data via Enrico control
    # Alice will also be Enrico via Enrico.from_alice
    # (see enrico_control_from_alice fixture)

    plaintext = "I'm bereaved, not a sap!"  # type: str
    enrico_request_data = {
        'message': b64encode(bytes(plaintext, encoding='utf-8')).decode(),
    }

    response = enrico_web_controller_from_alice.post('/encrypt_message', data=json.dumps(enrico_request_data))
    assert response.status_code == 200

    enrico_response_data = json.loads(response.data)
    assert 'message_kit' in enrico_response_data['result']

    kit_bytes = b64decode(enrico_response_data['result']['message_kit'].encode())
    bob_message_kit = MessageKit.from_bytes(kit_bytes)

    # Retrieve data via Bob control
    encoded_message_kit = b64encode(bytes(bob_message_kit)).decode()

    bob_request_data = {
        'policy_encrypting_key': policy_pubkey_enc_hex,
        'alice_verifying_key': alice_verifying_key_hex,
        'message_kit': encoded_message_kit,
        'encrypted_treasure_map': alice_response_data['result']['treasure_map']
    }

    # Give bob a node to remember
    teacher = list(federated_ursulas)[1]
    federated_bob.remember_node(teacher)

    response = bob_web_controller_test_client.post('/retrieve_and_decrypt', data=json.dumps(bob_request_data))
    assert response.status_code == 200

    bob_response_data = json.loads(response.data)
    assert 'cleartexts' in bob_response_data['result']

    for cleartext in bob_response_data['result']['cleartexts']:
        assert b64decode(cleartext.encode()).decode() == plaintext
