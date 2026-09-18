import os
import boto3
import json
from botocore.exceptions import ClientError
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import (
    ResourceNotFoundError,
    ClientAuthenticationError,
    HttpResponseError,
)
from dotenv import load_dotenv

load_dotenv()

class AWSSecretsManager:
    def __init__(self):
        """
        Initializes the AWSSecretsManager with a boto3 client.
        The AWS region is retrieved from the 'AWS_REGION' environment variable,
        defaulting to 'us-east-1' if not set.
        """
        region_name = os.environ.get("AWS_REGION", "us-east-1")
        self.session = boto3.session.Session()
        self.client = self.session.client(
            service_name='secretsmanager',
            region_name=region_name
        )

    def get_aws_secret(self, secret_name: str, secret_key: str = None):
        """
        Retrieves a secret from AWS Secrets Manager.
        :param secret_name: The name of the secret in AWS Secrets Manager.
        :param secret_key: The key of the secret to retrieve from the JSON object. If None, returns the entire secret string.
        """
        try:
            get_secret_value_response = self.client.get_secret_value(
                SecretId=secret_name
            )
        except ClientError as e:
            # For a list of exceptions thrown, see
            # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
            raise e

        # Decrypts secret using the associated KMS key.
        secret = get_secret_value_response['SecretString']

        if secret_key:
            secret_dict = json.loads(secret)
            return secret_dict.get(secret_key)
        return secret


class AzureKeyVaultSecretsManager:
    def __init__(self):
        """
        Initializes the AzureKeyVaultSecretsManager with DefaultAzureCredential
        and Key Vault URL from environment variables.
        """
        key_vault_url = os.getenv("AZURE_KEY_VAULT_URL")

        if not key_vault_url:
            raise ValueError(
                "AZURE_KEY_VAULT_URL is required when CLOUD_PROVIDER is set to AZURE."
            )

        self.client = SecretClient(
            vault_url=key_vault_url,
            credential=DefaultAzureCredential(additionally_allowed_tenants=["*"])
        )

    def get_azure_secret(self, secret_name: str, secret_key: str = None):
        """
        Retrieves a secret from Azure Key Vault.
        :param secret_name: The name of the secret in Azure Key Vault.
        :param secret_key: The key of the secret to retrieve from the JSON object. If None, returns the entire secret string.
        """
        try:
            secret = self.client.get_secret(secret_name).value
        except ResourceNotFoundError:
            raise ValueError(f"Secret '{secret_name}' was not found in Azure Key Vault.")
        except ClientAuthenticationError:
            raise ValueError(
                "Authentication failed for Azure Key Vault. Please check your Azure "
                "login, managed identity, or service principal environment variables."
            )
        except HttpResponseError as e:
            raise ValueError(f"Azure Key Vault request failed: {e}")

        if secret_key:
            secret_dict = json.loads(secret)
            return secret_dict.get(secret_key)
        return secret

class SecretsManager:
    def __init__(self):
        """
        Initializes the SecretsManager based on the configured cloud provider.
        Supported values for CLOUD_PROVIDER are AWS and AZURE.
        """
        cloud_provider = os.getenv("CLOUD_PROVIDER")

        if not cloud_provider:
            raise ValueError("CLOUD_PROVIDER must be set to AWS or AZURE.")

        cloud_provider = cloud_provider.upper()

        if cloud_provider == "AZURE":
            self.manager = AzureKeyVaultSecretsManager()
        elif cloud_provider == "AWS":
            self.manager = AWSSecretsManager()
        else:
            raise ValueError("CLOUD_PROVIDER must be set to AWS or AZURE.")

    def get_secret(self, secret_name: str, secret_key: str = None):
        """
        Retrieves a secret from the configured secret manager.
        :param secret_name: The name of the secret in the configured secret manager.
        :param secret_key: The key of the secret to retrieve from the JSON object. If None, returns the entire secret string.
        """
        cloud_provider = os.getenv("CLOUD_PROVIDER")

        if not cloud_provider:
            raise ValueError("CLOUD_PROVIDER must be set to AWS or AZURE.")

        cloud_provider = cloud_provider.upper()

        if cloud_provider == "AZURE":
            return self.manager.get_azure_secret(secret_name, secret_key)
        if cloud_provider == "AWS":
            return self.manager.get_aws_secret(secret_name, secret_key)
        raise ValueError("CLOUD_PROVIDER must be set to AWS or AZURE.")
