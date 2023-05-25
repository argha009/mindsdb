import json
import pandas as pd
from typing import Dict

from mindsdb.integrations.handlers.frappe_handler.frappe_tables import FrappeDocumentsTable
from mindsdb.integrations.handlers.frappe_handler.frappe_client import FrappeClient
from mindsdb.integrations.libs.api_handler import APIHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
)
from mindsdb.utilities import log
from mindsdb_sql import parse_sql


class FrappeHandler(APIHandler):
    """A class for handling connections and interactions with the Frappe API.

    Attributes:
        client (FrappeClient): The `FrappeClient` object for interacting with the Frappe API.
        is_connected (bool): Whether or not the API client is connected to Frappe.
        domain (str): Frappe domain to send API requests to.
        access_token (str): OAuth token to use for authentication.
    """

    def __init__(self, name: str = None, **kwargs):
        """Registers all API tables and prepares the handler for an API connection.

        Args:
            name: (str): The handler name to use
        """
        super().__init__(name)
        self.client = None
        self.is_connected = False

        args = kwargs.get('connection_data', {})
        if not 'access_token' in args:
            raise ValueError('"access_token" parameter required for authentication')
        if not 'domain' in args:
            raise ValueError('"domain" parameter required to connect to your Frappe instance')
        self.access_token = args['access_token']
        self.domain = args['domain']

        document_data = FrappeDocumentsTable(self)
        self._register_table('documents', document_data)

    def connect(self) -> FrappeClient:
        """Creates a new  API client if needed and sets it as the client to use for requests.

        Returns newly created Frappe API client, or current client if already set.
        """
        if self.is_connected is True and self.client:
            return self.client

        if self.domain and self.access_token:
            self.client = FrappeClient(self.domain, self.access_token)

        self.is_connected = True
        return self.client

    def back_office_config(self):
        tools = {
            'claim_expense': '''
             is used to expense claim. Input is:
                - There are two columns: doctype, data
                - The doctype column will be "Expense Claim"
                - The data column will be a JSON object serialized as a string
                
                This is the list of fields in the data JSON object:
                    a. [required] posting_date
                    b. [required] company
                    c. [required] employee
                    d. [required] expenses
                    
                The expenses field is a list of expense JSON objects. Here is a list of fields in an expense JSON object:
                    a. [required] expense_date
                    b. [required] expense_type
                    c. [required] amount
                    d. [required] sanctioned_amount
            ''',
            'company_exists': '''
                is used to check company is exist. Input is company name
            ''',
            'employee_code_exists': '''
                is used to check employee is exist. Input is employee code
            '''
        }

        options = {
            'Create new expense claim': '''
                - ask user has to provide all fields to fill input json.
                - company name has to be checked with company_exists tool
                - employee name has to be checked with employee_code_exists tool
                - after all validations claim_expense tool has to be used to create expense claim.
            '''
        }

        context = {
            # 'allowed expenses types': ['Travel', 'Food']
        }
        return {
            'tools': tools,
            'options': options,
            'context': context
        }

    def company_exists(self, name):
        if name not in ['CloudE8']:
            return False
        return True

    def employee_code_exists(self, name):
        if name not in ['HR-EMP-00001']:
            return False
        return True

    def claim_expense(self, data):
        self.call_frappe_api('create_document', **data)

    def check_connection(self) -> StatusResponse:
        """Checks connection to Frappe API by sending a ping request.

        Returns StatusResponse indicating whether or not the handler is connected.
        """

        response = StatusResponse(False)

        try:
            client = self.connect()
            client.ping()
            response.success = True

        except Exception as e:
            log.logger.error(f'Error connecting to Frappe API: {e}!')
            response.error_message = e

        self.is_connected = response.success
        return response

    def native_query(self, query: str = None) -> Response:
        ast = parse_sql(query, dialect='mindsdb')
        return self.query(ast)

    def _document_to_dataframe_row(self, doctype, document: Dict) -> Dict:
        return {
            'doctype': doctype,
            'data': json.dumps(document)
        }

    def _get_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        document = client.get_document(doctype, params['name'])
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, document)])

    def _get_documents(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        limit = None
        filters = None
        doctype = params['doctype']
        if 'limit' in params:
            limit = params['limit']
        if 'filters' in params:
            filters = params['filters']
        documents = client.get_documents(doctype, limit=limit, filters=filters)
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, d) for d in documents])

    def _create_document(self, params: Dict = None) -> pd.DataFrame:
        client = self.connect()
        doctype = params['doctype']
        new_document = client.post_document(doctype, json.loads(params['data']))
        return pd.DataFrame.from_records([self._document_to_dataframe_row(doctype, new_document)])

    def call_frappe_api(self, method_name: str = None, params: Dict = None) -> pd.DataFrame:
        """Calls the Frappe API method with the given params.

        Returns results as a pandas DataFrame.

        Args:
            method_name (str): Method name to call (e.g. get_document)
            params (Dict): Params to pass to the API call
        """
        if method_name == 'get_documents':
            return self._get_documents(params)
        if method_name == 'get_document':
            return self._get_document(params)
        if method_name == 'create_document':
            return self._create_document(params)
        raise NotImplementedError('Method name {} not supported by Frappe API Handler'.format(method_name))
