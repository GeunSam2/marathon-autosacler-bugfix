import logging
import os
import json
import sys
import time
import math
import argparse
import urllib3

from autoscaler.agent_stats import AgentStats
from autoscaler.api_client import APIClient
from autoscaler.app import MarathonApp
from autoscaler.modes.scalecpu import ScaleByCPU
from autoscaler.modes.scalesqs import ScaleBySQS
from autoscaler.modes.scalemem import ScaleByMemory
from autoscaler.modes.scalecpuandmem import ScaleByCPUAndMemory
from autoscaler.modes.scalebycpuormem import ScaleByCPUOrMemory

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Autoscaler:
    """Marathon autoscaler upon initialization, it reads a list of
    command line parameters or env variables. Then it logs in to DCOS
    and starts querying metrics relevant to the scaling objective
    (cpu, mem, sqs, and, or). Scaling can happen by cpu, mem,
    or sqs. The checks are performed on a configurable interval.
    """

    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    MARATHON_APPS_URI = '/service/marathon/v2/apps'

    # Dictionary defines the different scaling modes available to autoscaler
    MODES = {
        'sqs': ScaleBySQS,
        'cpu': ScaleByCPU,
        'mem': ScaleByMemory,
        'and': ScaleByCPUAndMemory,
        'or': ScaleByCPUOrMemory
    }

    def __init__(self):
        """Initialize the object with data from the command line or environment
        variables. Log in into DCOS if username / password are provided.
        Set up logging according to the verbosity requested.
        """

        self.scale_up = 0
        self.cool_down = 0

        args = self.parse_arguments()

        self.dcos_master = args.dcos_master
        self.trigger_mode = args.trigger_mode
        self.autoscale_multiplier = float(args.autoscale_multiplier)
        self.min_instances = int(args.min_instances)
        self.max_instances = int(args.max_instances)
        self.cool_down_factor = int(args.cool_down_factor)
        self.scale_up_factor = int(args.scale_up_factor)
        self.interval = args.interval
        self.verbose = args.verbose or os.environ.get("AS_VERBOSE")

        # Start logging
        if self.verbose:
            level = logging.DEBUG
        else:
            level = logging.INFO

        logging.basicConfig(
            level=level,
            format=self.LOGGING_FORMAT
        )

        self.log = logging.getLogger("autoscale")

        # Initialize marathon client for auth requests
        self.api_client = APIClient(self.dcos_master)

        # Initialize agent statistics fetcher and keeper
        self.agent_stats = AgentStats(self.api_client)

        # Instantiate the Marathon app class
        app_name = args.marathon_app
        if not app_name.startswith('/'):
            app_name = '/' + app_name
        self.marathon_app = MarathonApp(
            app_name=app_name,
            api_client=self.api_client
        )

        # Instantiate the scaling mode class
        if self.MODES.get(self.trigger_mode, None) is None:
            self.log.error("Scale mode is not found.")
            sys.exit(1)

        min = [float(i) for i in args.min_range.split(',')]
        max = [float(i) for i in args.max_range.split(',')]

        dimension = {"min": min, "max": max}

        self.scaling_mode = self.MODES[self.trigger_mode](
            api_client=self.api_client,
            agent_stats=self.agent_stats,
            app=self.marathon_app,
            dimension=dimension,
        )

    def timer(self):
        """Simple timer function"""
        self.log.debug("Successfully completed a cycle, sleeping for %s seconds",
                       self.interval)
        time.sleep(self.interval)

    def autoscale(self, direction):
        """ Determine if scaling mode direction is below or above scaling
        factor. If scale_up/cool_down cycle count exceeds scaling
        factor, autoscale (up/down) will be triggered.
        """

        if direction == 1:
            self.scale_up += 1
            self.cool_down = 0
            if self.scale_up >= self.scale_up_factor:
                self.log.info("Auto-scale triggered based on %s exceeding threshold" % self.trigger_mode)
                self.scale_app(True)
                self.scale_up = 0
            else:
                self.log.info("%s above thresholds, but waiting to exceed scale-up factor. "
                              "Consecutive cycles = %s, Scale-up factor = %s" %
                              (self.trigger_mode, self.scale_up, self.scale_up_factor))
        elif direction == -1:
            self.cool_down += 1
            self.scale_up = 0
            if self.cool_down >= self.cool_down_factor:
                self.log.info("Auto-scale triggered based on %s below the threshold" % self.trigger_mode)
                self.scale_app(False)
                self.cool_down = 0
            else:
                self.log.info("%s below thresholds, but waiting to exceed cool-down factor. "
                              "Consecutive cycles = %s, Cool-down factor = %s" %
                              (self.trigger_mode, self.cool_down, self.cool_down_factor))
        else:
            self.log.info("%s within thresholds" % self.trigger_mode)
            self.scale_up = 0
            self.cool_down = 0

    def scale_app(self, is_up):
        """Scale marathon_app up or down
        Args:
            is_up(bool): Scale up if True, scale down if False
        """
        # get the number of instances running
        app_instances = self.marathon_app.get_app_instances()

        if is_up:
            target_instances = math.ceil(app_instances * self.autoscale_multiplier)
            if target_instances > self.max_instances:
                self.log.info("Reached the set maximum of instances %s", self.max_instances)
                target_instances = self.max_instances
        else:
            target_instances = math.floor(app_instances / self.autoscale_multiplier)
            if target_instances < self.min_instances:
                self.log.info("Reached the set minimum of instances %s", self.min_instances)
                target_instances = self.min_instances

        self.log.debug("scale_app: app_instances %s target_instances %s",
                       app_instances, target_instances)

        if app_instances != target_instances:
            data = {'instances': target_instances}
            json_data = json.dumps(data)
            response = self.api_client.dcos_rest(
                "put",
                '/service/marathon/v2/apps' + self.marathon_app.app_name,
                data=json_data
            )
            self.log.debug("scale_app response: %s", response)

    def parse_arguments(self):
        """Set up an argument parser
        Override values of command line arguments with environment variables.
        """
        parser = argparse.ArgumentParser(description='Marathon autoscale_examples app.')
        parser.set_defaults()
        parser.add_argument('--dcos-master',
                            help=('The DNS hostname or IP of your Marathon'
                                  ' Instance'),
                            **self.env_or_req('AS_DCOS_MASTER'))
        parser.add_argument('--trigger_mode',
                            help=('Which metric(s) to trigger Autoscale '
                                  '(cpu, mem, sqs)'),
                            **self.env_or_req('AS_TRIGGER_MODE'))
        parser.add_argument('--autoscale_multiplier',
                            help=('Autoscale multiplier for triggered '
                                  'Autoscale (ie 2)'),
                            **self.env_or_req('AS_AUTOSCALE_MULTIPLIER'), type=float)
        parser.add_argument('--max_instances',
                            help=('The Max instances that should ever exist'
                                  ' for this application (ie. 20)'),
                            **self.env_or_req('AS_MAX_INSTANCES'), type=int)
        parser.add_argument('--marathon-app',
                            help=('Marathon Application Name to Configure '
                                  'Autoscale for from the Marathon UI'),
                            **self.env_or_req('AS_MARATHON_APP'))
        parser.add_argument('--min_instances',
                            help='Minimum number of instances to maintain',
                            **self.env_or_req('AS_MIN_INSTANCES'), type=int)
        parser.add_argument('--cool_down_factor',
                            help='Number of cycles to avoid scaling again',
                            **self.env_or_req('AS_COOL_DOWN_FACTOR'), type=int)
        parser.add_argument('--scale_up_factor',
                            help='Number of cycles to avoid scaling again',
                            **self.env_or_req('AS_SCALE_UP_FACTOR'), type=int)
        parser.add_argument('--interval',
                            help=('Time in seconds to wait between '
                                  'checks (ie. 20)'),
                            **self.env_or_req('AS_INTERVAL'), type=int)
        parser.add_argument('--min_range',
                            help=('The minimum range of the scaling modes '
                                  'dimension.'),
                            **self.env_or_req('AS_MIN_RANGE'), type=str)
        parser.add_argument('--max_range',
                            help=('The maximum range of the scaling modes '
                                  'dimension'),
                            **self.env_or_req('AS_MAX_RANGE'), type=str)
        parser.add_argument('-v', '--verbose', action="store_true",
                            help='Display DEBUG messages')

        try:
            args = parser.parse_args()
            return args
        except argparse.ArgumentError as arg_err:
            sys.stderr.write(arg_err)
            parser.print_help()
            sys.exit(1)

    @staticmethod
    def env_or_req(key):
        """Environment variable substitute
        Args:
            key (str): Name of environment variable to look for
        Returns:
            string to be included in parameter parsing configuration
        """
        if os.environ.get(key):
            result = {'default': os.environ.get(key)}
        else:
            result = {'required': True}
        return result

    def run(self):
        """Main function
        """
        self.cool_down = 0
        self.scale_up = 0

        while True:

            try:
                self.agent_stats.reset()

                # Test for apps existence in Marathon
                if not self.marathon_app.app_exists():
                    self.log.error("Could not find %s in list of apps.",
                                   self.marathon_app.app_name)
                    continue

                # Get the mode scaling direction
                direction = self.scaling_mode.scale_direction()
                self.log.debug("scaling mode direction = %s", direction)

                # Evaluate whether to auto-scale
                self.autoscale(direction)

            except Exception as e:
                self.log.exception(e)
            finally:
                self.timer()


if __name__ == "__main__":
    AutoScaler = Autoscaler()
    AutoScaler.run()
