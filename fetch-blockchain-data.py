import os
import json
import yaml
import vercel_blob
from datetime import datetime
from substrateinterface import SubstrateInterface


class FetchBlockchainData:
    def __init__(self, rpc_file):
        """
        Initialize the checker with an RPC config file

        Args:
            rpc_file (str): Path to YAML file containing RPC endpoints
        """
        with open(rpc_file, 'r') as f:
            self.networks = yaml.safe_load(f)
            print(self.networks)

    def connect_to_network(self, url):
        """
        Establish connection to a substrate network

        Args:
            url (str): RPC endpoint URL

        Returns:
            SubstrateInterface: Connected substrate interface
        """
        try:
            substrate = SubstrateInterface(url=url, ws_options={'timeout': 15})
            return substrate
        except Exception as e:
            print(f"Failed to connect to {url}: {str(e)}")
            return None

    def get_block_epoch(self, block_number, substrate):
        block_hash = substrate.get_block_hash(block_number)
        epoch = substrate.query(
            module='Timestamp',
            storage_function='Now',
            block_hash=block_hash,
        )

        return datetime.fromtimestamp(epoch.value / 1000).strftime('%Y-%m-%d')

    def check_democracy_proposal(self, substrate):
        """
        Check latest referendum in democracy module
        """
        try:
            # Get the latest referendum index
            referendum_count = substrate.query(
                module='Democracy',
                storage_function='ReferendumCount'
            ).value

            if referendum_count:
                # Get info about the latest referendum
                latest_ref = substrate.query(
                    module='Democracy',
                    storage_function='ReferendumInfoOf',
                    params=[referendum_count - 1]
                )

                result = {
                    'type': 'democracy',
                    'index': referendum_count - 1,
                    'total_count': referendum_count,
                    'info': latest_ref.value
                }

                # Add timestamp for finished proposals
                if latest_ref.value and 'Finished' in latest_ref.value:
                    end_block = latest_ref.value['Finished']['end']
                    result['ended_at'] = self.get_block_epoch(end_block, substrate)

                print("✅ Gov1")
                return result

            return {
                'type': 'democracy',
                'total_count': 0,  # No proposals
                'info': None
            }
        except Exception as error:
            print(f"❌ Gov1: {error}")
            return None

    def check_opengov_proposal(self, substrate):
        """
        Check latest referendum in OpenGov system
        """
        try:
            # Get the latest referendum index
            referendum_count = substrate.query(
                module='Referenda',
                storage_function='ReferendumCount'
            ).value

            if referendum_count:
                # Get info about the latest referendum
                latest_ref = substrate.query(
                    module='Referenda',
                    storage_function='ReferendumInfoFor',
                    params=[referendum_count - 1]
                )

                result = {
                    'type': 'opengov',
                    'index': referendum_count - 1,
                    'total_count': referendum_count,
                    'info': latest_ref.value
                }

                # Add timestamp for approved proposals
                if latest_ref.value and 'Approved' in latest_ref.value:
                    end_block = latest_ref.value['Approved'][0]  # First item in array is block number
                    result['ended_at'] = self.get_block_epoch(end_block, substrate)

                print("✅ Gov2")
                return result

            return {
                'type': 'opengov',
                'total_count': 0,  # No proposals
                'info': None
            }
        except Exception as error:
            print(f"❌ Gov2: {error}")
            return None

    def check_all_networks(self):
        """
        Check all networks defined in the RPC file for latest proposals

        Returns:
            dict: Results for each network
        """
        results = {}

        for network_name, network_info in self.networks.items():
            print(f"\nChecking {network_name}...")
            substrate = self.connect_to_network(network_info['url'])

            if not substrate:
                continue

            # Try both democracy and OpenGov
            democracy_result = self.check_democracy_proposal(substrate)
            opengov_result = self.check_opengov_proposal(substrate)

            results[network_name] = {
                'url': network_info['url'],
                'democracy': democracy_result,
                'opengov': opengov_result,
                'last_checked': datetime.now().isoformat()
            }

        return results

    @staticmethod
    def upload_to_vercel_blob(results, output_file):
        """
        Save results to Vercel Blob storage

        Args:
            results (dict): Results to save
            output_file (str): Name to use for the blob
        """
        try:
            # Get the token from environment
            token = os.environ.get('BLOB_READ_WRITE_TOKEN')
            if not token:
                raise Exception('BLOB_READ_WRITE_TOKEN environment variable not set')

            json_data = json.dumps(results, indent=2).encode('utf-8')

            # Upload to Vercel Blob
            response = vercel_blob.put(
                path=output_file,
                data=json_data,
                options={
                    'token': token,
                    'addRandomSuffix': 'false',  # consistent filename
                    'cacheControlMaxAge': '3600'  # 1 hour cache
                }
            )

            print(f"Data uploaded to: {response.get('url')}")
            return response.get('url')

        except Exception as e:
            print(f"Error saving to blob: {e}")
            raise


if __name__ == '__main__':
    # Initialize and run the checker
    fetch_blockchain_data = FetchBlockchainData('networks.yaml')
    results = fetch_blockchain_data.check_all_networks()
    fetch_blockchain_data.upload_to_vercel_blob(results, 'proposal_results.json')
