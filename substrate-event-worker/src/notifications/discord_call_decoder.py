import logging
import discord
from scalecodec.base import ScaleBytes
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MaterializedChainState:
    def __init__(self, substrate):
            self.substrate = substrate

    def ref_caller(self, index: int, gov1: bool, call_data: bool):
        """
        Retrieves and decodes the referendum call data based on given parameters.

        Args:
            index (int): The index of the referendum to query.
            gov1 (bool): Determines which module to query ('Democracy' if True, 'Referenda' if False).
            call_data (bool): Determines the type of data to return (raw call data if True, decoded call data if False).

        Returns:
            tuple: A tuple containing a boolean indicating success or failure, and the decoded call data or error message.

        Raises:
            Exception: If an error occurs during the retrieval or decoding process.
        """
        try:
            referendum = self.substrate.query(module="Democracy" if gov1 else "Referenda",
                                              storage_function="ReferendumInfoOf" if gov1 else "ReferendumInfoFor",
                                              params=[index]).serialize()

            if referendum is None or 'Ongoing' not in referendum:
                return False, f":warning: Referendum **#{index}** is inactive"

            preimage = referendum['Ongoing']['proposal']

            if 'Inline' in preimage:
                call = preimage['Inline']
                if not call_data:
                    call_obj = self.substrate.create_scale_object('Call')
                    decoded_call = call_obj.decode(ScaleBytes(call))
                    return decoded_call, preimage
                else:
                    return call

            if 'Lookup' in preimage:
                preimage_hash = preimage['Lookup']['hash']
                preimage_length = preimage['Lookup']['len']
                call = self.substrate.query(module='Preimage', storage_function='PreimageFor',
                                            params=[(preimage_hash, preimage_length)]).value

                if call is None:
                    return False, ":warning: Preimage not found on chain"

                if not call.isprintable():
                    call = f"0x{''.join(f'{ord(c):02x}' for c in call)}"

                if not call_data:
                    call_obj = self.substrate.create_scale_object('Call')
                    decoded_call = call_obj.decode(ScaleBytes(call))
                    return decoded_call, preimage_hash
                else:
                    return call
        except Exception as ref_caller_error:
            raise ref_caller_error


class ProcessCallData:
    def __init__(self, decimals):
        self.decimals = decimals
        self.general_index = None

    @staticmethod
    def format_key(key):
        """
        Formats a given key by splitting it on underscores, capitalizing each part except
        for those containing 'id' which are made uppercase, and then joining them back together
        with spaces in between.

        :param key: The key to be formatted.
        :type key: str
        :return: The formatted key.
        :rtype: str
        """
        parts = key.split('_')
        formatted_parts = []
        for part in parts:
            if "id" in part.lower():
                formatted_part = part.upper()
            else:
                formatted_part = part.capitalize()
            formatted_parts.append(formatted_part)
        return ' '.join(formatted_parts)

    def find_and_collect_values(self, data, preimagehash, indent=0, path='', current_embed=None):
        """
        Recursively traverses through the given data (list, dictionary or other data types)
        and collects certain values to be added to a list of discord Embed objects.
        The function modifies the given `embeds` list in-place,
        appending new Embed objects when required.

        :param data: The data to traverse
        :type data: list, dict or other
        :param preimagehash: The hash of the preimage associated with the data
        :type preimagehash: str
        :param indent: The current indentation level for formatting Embed descriptions, default is 0
        :type indent: int
        :param path: The path to the current data element, default is ''
        :type path: str
        :param current_embed: The currently active Embed object, default is None
        :type current_embed: Embed or None
        :return: The extended list of Embed objects
        :rtype: list
        """

        if current_embed is None:
            if data is False:
                description = preimagehash
            else:
                description = ""
            current_embed = discord.Embed(description=description, color=0x00ff00, timestamp=datetime.now(timezone.utc))

        max_description_length = 1000
        call_function = 0
        call_module = 0

        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{hash(key)}" if path else str(hash(key))

                if key == 'call_index':
                    continue

                if len(current_embed.description) >= max_description_length:
                    return current_embed

                if isinstance(value, (dict, list)):
                    self.find_and_collect_values(value, preimagehash, indent, new_path, current_embed)
                else:
                    value_str = str(value)

                    if key == 'call_function':
                        call_function = call_function + 1

                    if key == 'call_module':
                        call_module = call_module + 1

                    if key in ['X1', 'X2', 'X3', 'X4', 'X5']:
                        indent = indent + 1

                    if call_function == 1 and call_module == 0:
                        indent = indent + 1

                    if key == 'currency_id':
                        self.general_index = value

                    if key == 'GeneralIndex':
                        self.general_index = value

                    #print(f"{key:<20} {call_function:<15} {call_module:<15} {indent:<15} {len(current_embed.description):<15} {key not in ['call_function', 'call_module']}")  # debugging

                    if key not in ['call_function', 'call_module']:
                        if key == 'amount':
                            asset_dict = {  22: 'USDC',
                                            1337: 'USDC',
                                            10: 'USDT',
                                            1984: 'USDT' }
                            if str(self.general_index) in ['1337', '1984', '10', '22']:
                                decimal = 1e6
                            else:
                                decimal = self.decimals


                            asset_name = asset_dict.get(self.general_index)

                            value_str = float(value_str) / decimal
                            current_embed.description += f"\n{'　' * (indent + 1)} **{self.format_key(key)[:256]}**: {value_str:,.2f} `{asset_name}`"

                        elif key in ['beneficiary', 'signed', 'curator']:
                            current_embed.description += f"\n{'　' * (indent + 1)} **{self.format_key(key)[:256]}**: [{(value_str[:10] + '...' + value_str[-10:])}](https://polkadot.subscan.io/account/{value_str})"
                        else:
                            current_embed.description += f"\n{'　' * (indent + 1)} **{self.format_key(key)[:256]}**: {(value_str[:253] + '...') if len(value_str) > 256 else value_str}"
                    else:
                        current_embed.description += f"\n{'　' * indent} **{self.format_key(key)[:256]}**: `{value_str[:253]}`"

                    if len(current_embed.description) >= max_description_length:
                        return current_embed

                    self.find_and_collect_values(value, preimagehash, indent, new_path, current_embed)

        elif isinstance(data, (list, tuple)):
            for index, item in enumerate(data):
                if len(current_embed.description) >= max_description_length:
                    current_embed.description += (f"\n\nThe call is too large to display here. Visit [**Subscan**](https://polkadot.subscan.io/preimage/{preimagehash}) for more details")
                    return current_embed

                new_path = f"{path}[{index}]"
                self.find_and_collect_values(item, preimagehash, indent, new_path, current_embed)

        return current_embed

    def consolidate_call_args(self, data):
        """
        Modifies the given data in-place by consolidating 'call_args' entries
        from list of dictionaries into a single dictionary where the key is 'name'
        and the value is 'value'.

        :param data: The data to consolidate
        :type data: dict or list
        :return: The consolidated data
        :rtype: dict or list
        """
        if isinstance(data, dict):
            if "call_args" in data:
                new_args = {}
                for arg in data["call_args"]:
                    if "name" in arg and "value" in arg:
                        new_args[arg["name"]] = arg["value"]
                data["call_args"] = new_args
            for key, value in data.items():
                data[key] = self.consolidate_call_args(value)  # Recursive call for nested dictionaries
        elif isinstance(data, list):
            for index, item in enumerate(data):
                data[index] = self.consolidate_call_args(item)  # Recursive call for lists
        return data