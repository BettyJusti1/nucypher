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

from marshmallow import fields

from nucypher.characters.control.specifications.exceptions import InvalidNativeDataTypes
from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields.base import BaseField
from nucypher.policy.hrac import HRAC as HRACClass


class HRAC(BaseField, fields.String):

    def _serialize(self, value, attr, obj, **kwargs):
        return bytes(value).hex()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return bytes.fromhex(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to a valid HRAC serialization: {e}")

    def _validate(self, value):
        try:
            HRACClass.from_bytes(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to a valid HRAC: {e}")
