import json
import logging.config
import unittest
import flask
from flask_restful import Api
from na3x.data.generator import Generator
from na3x.db.connect import MongoDb
from na3x.db.data import Accessor, AccessParams
from na3x.integration.importer import Importer
from na3x.transformation.transformer import Transformer
from na3x.utils.cfg import CfgUtils
import na3x.cfg
from logic.constants import DbConstants, RestConstants
from logic.entities import Sprint, Backlog, SprintTimeline, ComponentList, GroupList, EmployeeList, Group, \
    AllocationtList, Allocation, AllocationValidation

CFG_LOG_TEST = './cfg/log/test-logging-config.json'
CFG_DATA_GENERATION  = './cfg/data/jira-data-generation.json'
CFG_DATA_CLEANUP  = './cfg/data/jira-data-cleanup.json'
CFG_NA3X = './cfg/na3x.json'
CFG_KEY_JIRA_LOGIN = 'jira_login'
CFG_KEY_JIRA_PSWD = 'jira_pswd'
CFG_KEY_SCRUM_SPRINT = 'scrum_sprint'
CFG_TEST_DATA_DB = 'db_src_data'
CFG_TEST_DATA_COL_SPRINT = 'data.sprint'
CFG_TEST_DATA_SPRINT_ID = 'id'

with open(CFG_LOG_TEST) as logging_cfg_file:
    logging.config.dictConfig(json.load(logging_cfg_file, strict=False))
with open(CFG_NA3X) as na3x_cfg_file:
    na3x.cfg.init(json.load(na3x_cfg_file, strict=False))


def setUpModule():
    na3x.cfg.IS_TEST = True
    test_env_cfg = na3x.cfg.get_env_params()
    with open(CFG_DATA_GENERATION) as cfg_file:
        Generator(json.load(cfg_file, strict=False), test_env_cfg[CFG_KEY_JIRA_LOGIN],
              test_env_cfg[CFG_KEY_JIRA_PSWD], test_env_cfg).perform()


def tearDownModule():
    test_env_cfg = na3x.cfg.get_env_params()
    with open(CFG_DATA_CLEANUP) as cfg_file:
        Generator(json.load(cfg_file, strict=False), test_env_cfg[CFG_KEY_JIRA_LOGIN],
              test_env_cfg[CFG_KEY_JIRA_PSWD], test_env_cfg).perform()


class ImportTestCase(unittest.TestCase):
    __CFG_IMPORT = './cfg/jira/jira-import-scope.json'
    __CFG_IMPORT_DB = 'db_jira_import'
    __COL_BACKLOG = 'backlog'
    __COL_SPRINT = 'sprint'
    __COL_EMPLOYEES = 'employees'
    __COL_COMPONENTS = 'components'

    def setUp(self):
        logger = logging.getLogger(__name__)
        self.__test_env_cfg = na3x.cfg.get_env_params()
        self.__test_env_cfg[CFG_KEY_SCRUM_SPRINT] = Accessor.factory(CFG_TEST_DATA_DB).get(
            {AccessParams.KEY_COLLECTION: CFG_TEST_DATA_COL_SPRINT,
             AccessParams.KEY_TYPE: AccessParams.TYPE_SINGLE})[CFG_TEST_DATA_SPRINT_ID]
        try:
            logger.info('Init JIRA test data importer: {}'.format(ImportTestCase.__CFG_IMPORT))
            with open(ImportTestCase.__CFG_IMPORT) as cfg_file:
                cfg = json.loads(CfgUtils.substitute_params(cfg_file.read(), self.__test_env_cfg))
            Importer(cfg, self.__test_env_cfg[CFG_KEY_JIRA_LOGIN], self.__test_env_cfg[CFG_KEY_JIRA_PSWD]).perform()
        except Exception as e:
            logging.error(e, exc_info=True)
        self.__collections = MongoDb(self.__test_env_cfg[ImportTestCase.__CFG_IMPORT_DB]).connection.collection_names()

    def test_import_backlog(self):
        self.assertIn(ImportTestCase.__COL_BACKLOG, self.__collections)

    def test_import_sprint(self):
        self.assertIn(ImportTestCase.__COL_SPRINT, self.__collections)

    def test_import_employees(self):
        self.assertIn(ImportTestCase.__COL_EMPLOYEES, self.__collections)

    def test_import_components(self):
        self.assertIn(ImportTestCase.__COL_COMPONENTS, self.__collections)


class TransformTestCase(unittest.TestCase):
    __CFG_TRANSFORM = './cfg/scrum/scrum-import-scope-transform.json'
    __CFG_TRANSFORM_DB = 'db_scrum_api'

    def setUp(self):
        logger = logging.getLogger(__name__)
        self.__test_env_cfg = na3x.cfg.get_env_params()
        # ToDo: cleanup tables
        try:
            logger.info('Init transformer: {}'.format(TransformTestCase.__CFG_TRANSFORM))
            with open(TransformTestCase.__CFG_TRANSFORM) as cfg_file:
                Transformer(json.load(cfg_file, strict=False)).transform_data()
        except Exception as e:
            logging.error(e, exc_info=True)
        self.__collections = MongoDb(self.__test_env_cfg[TransformTestCase.__CFG_TRANSFORM_DB]).connection.collection_names()

    def test_transform_project_components(self):
        self.assertIn(DbConstants.PROJECT_COMPONENTS, self.__collections)

    def test_transform_project_employees(self):
        self.assertIn(DbConstants.PROJECT_EMPLOYEES, self.__collections)

    def test_transform_project_team(self):
        self.assertIn(DbConstants.PROJECT_TEAM, self.__collections) # ToDo: check if required / move to export test ?

    def test_transform_sprint_definition(self):
        self.assertIn(DbConstants.SCRUM_SPRINT, self.__collections)

    def test_transform_sprint_timeline(self):
        self.assertIn(DbConstants.SCRUM_SPRINT_TIMELINE, self.__collections)

    def test_transform_sprint_backlog(self):
        self.assertIn(DbConstants.SCRUM_SPRINT_BACKLOG, self.__collections)


class ApiTestCase(unittest.TestCase):
    __TEST_DATA_SPRINT = b'TEST sprint'
    __TEST_DATA_ISSUE = b'TEST-1'
    __TEST_DATA_EMPLOYEE = b'testuser'

    def setUp(self):
        self.__test_env_cfg = na3x.cfg.get_env_params()
        self.__app = flask.Flask(__name__)
        api = Api(self.__app)
        api.add_resource(Sprint, RestConstants.ROUTE_SPRINT)
        api.add_resource(SprintTimeline, RestConstants.ROUTE_SPRINT_TIMELINE)
        api.add_resource(Backlog, RestConstants.ROUTE_BACKLOG)
        api.add_resource(ComponentList, RestConstants.ROUTE_COMPONENTS)
        api.add_resource(GroupList, RestConstants.ROUTE_TEAM)
        api.add_resource(EmployeeList, RestConstants.ROUTE_EMPLOYEES)
        # ToDo: add coverage
        api.add_resource(Group, RestConstants.ROUTE_GROUP, '{}/<group>'.format(RestConstants.ROUTE_GROUP))
        api.add_resource(AllocationtList, RestConstants.ROUTE_ALLOCATIONS)
        api.add_resource(Allocation, RestConstants.ROUTE_ALLOCATION,
                         '{}/<key>,<date>,<group>,<employee>'.format(RestConstants.ROUTE_ALLOCATION))
        api.add_resource(AllocationValidation, RestConstants.ROUTE_ALLOCATION_VALIDATION)

    def test_api_sprint(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_SPRINT)
        self.assertEqual(result.status_code, 200)
        self.assertIn(ApiTestCase.__TEST_DATA_SPRINT, result.get_data())

    def test_api_sprint_timeline(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_SPRINT_TIMELINE)
        self.assertEqual(result.status_code, 200)

    def test_api_components(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_COMPONENTS)
        self.assertEqual(result.status_code, 200)

    def test_api_team(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_TEAM)
        self.assertEqual(result.status_code, 200)

    def test_api_employees(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_EMPLOYEES)
        self.assertEqual(result.status_code, 200)
        self.assertIn(ApiTestCase.__TEST_DATA_EMPLOYEE, result.get_data())

    def test_api_backlog(self):
        result = self.__app.test_client().get(RestConstants.ROUTE_BACKLOG)
        self.assertEqual(result.status_code, 200)
        self.assertIn(ApiTestCase.__TEST_DATA_ISSUE, result.get_data())


if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTest(ImportTestCase)
    suite.addTest(TransformTestCase)
    suite.addTest(ApiTestCase)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
