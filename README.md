# marathon-autoscale
Dockerized auto-scaler application that can be run under Marathon management to dynamically scale a service running on DC/OS.

## Prerequisites
1. A running DC/OS cluster
2. DC/OS CLI installed on your local machine

If running on a DC/OS cluster in Permissive or Strict mode, an user or service account with the appropriate permissions to modify Marathon jobs.  An example script for setting up a service account can be found in create-service-account.sh

## Installation/Configuration

### Building the Docker container

How to build the container:

    image_name="mesosphere/marathon-autoscale" make
    image_name="mesosphere/marathon-autoscale" make push

There is also a image available at docker hub for [mesosphere/marathon-autoscaler](https://hub.docker.com/r/mesosphere/marathon-autoscaler/)

### (Optional) Creating a service account

The create_service_account.sh script takes two parameters:

    Service-Account-Name #the name of the service account you want to create
    Namespace-Path #the path to launch this service under marathon management.  e.g. / or /dev

    $ ./create-service-account.sh [service-account-name] [namespace-path]

### Install from the DC/OS Catalog

The marathon-autoscaler can be installed as a service from the DC/OS catalog with `dcos package install marathon-autoscaler`.  There is no default installation for this service.  The autoscaler needs to know a number of things in order to scale an application.   The DC/OS package install process for this service requires a configuration options during installation.   Assuming a simple `/sleep` application running in Marathon and the following config.json file:

```
{
  "autoscaler": {
    "marathon-app" : "/sleepy",
    "userid": "agent-99",
    "password": "secret"
  }
}
```

All the configurations listed below are available to be changed via the config.json file.   The default name of this service is ${marathon-app}-autoscaler in this case, the service is `/sleepy-autoscaler`.

### Marathon examples

#### Autoscale examples
Update one of the definitions in the [Marathon definitions](marathon_definitions/autoscale_examples/) folder to match your specific configuration. Marathon application names must include the forward slash. This modification was made in order to handle applications within service groups. (e.g. /group/hello-dcos)

Core environment variables available to the application:

    AS_DCOS_MASTER # hostname of dcos master
    AS_MARATHON_APP # app to autoscale

    AS_TRIGGER_MODE # scaling mode (cpu | mem | sqs | and | or)

    AS_AUTOSCALE_MULTIPLIER # The number by which current instances will be multiplied (scale-out) or divided (scale-in). This determines how many instances to add during scale-out, or remove during scale-in.
    AS_MIN_INSTANCES # min number of instances, don’t make less than 2
    AS_MAX_INSTANCES # max number of instances, must be greater than AS_MIN_INSTANCES

    AS_COOL_DOWN_FACTOR # how many times should we poll before scaling down
    AS_SCALE_UP_FACTOR # how many times should we poll before scaling up
    AS_INTERVAL #how often should we poll in seconds

**Notes**

If you are using an authentication:

    AS_USERID # username of the user or service account with access to scale the service
    --and either--
    AS_PASSWORD: secret0 # password of the userid above ideally from the secret store
    AS_SECRET: secret0 # private key of the userid above ideally from the secret store

If you are using CPU as your scaling mode:

    AS_MAX_RANGE # max average cpu time as float, e.g. 80 or 80.5
    AS_MIN_RANGE # min average cpu time as float, e.g. 55 or 55.5

If you are using Memory as your scaling mode:

    AS_MAX_RANGE # max avg mem utilization percent as float, e.g. 75 or 75.0
    AS_MIN_RANGE # min avg mem utilization percent as float, e.g. 55 or 55.0

If you are using AND (CPU and Memory) as your scaling mode:

    AS_MAX_RANGE # [max average cpu time, max avg mem utilization percent], e.g. 75.0,80.0
    AS_MIN_RANGE # [min average cpu time, min avg men utilization percent], e.g. 55.0,55.0

If you are using OR (CPU or Memory) as your scaling mode:

    AS_MAX_RANGE # [max average cpu time, max avg mem utilization percent], e.g. 75.0,80.0
    AS_MIN_RANGE # [min average cpu time, min avg men utilization percent], e.g. 55.0,55.0

If you are using SQS as your scaling mode:

    AS_QUEUE_URL # full URL of the SQS queue
    AWS_ACCESS_KEY_ID # aws access key
    AWS_SECRET_ACCESS_KEY # aws secret key
    AWS_DEFAULT_REGION # aws region
    AS_MIN_RANGE # min number of available messages in the queue
    AS_MAX_RANGE # max number of available messages in the queue

#### Target application examples
In order to create artificial stress for an application, use one of the examples located in the [Marathon Target Application](marathon_definitions/target_app_examples/) folder.

## Program Execution / Usage

Add your application to Marathon using the DC/OS Marathon CLI.

    $ dcos marathon app add marathon_defs/marathon.json

Where the marathon.json has been built from one of the samples:

    autoscale-cpu-noauth-marathon.json #security disabled or OSS DC/OS
    autoscale-mem-noauth-marathon.json #security disabled or OSS DC/OS
    autoscale-sqs-noauth-marathon.json #security disabled or OSS DC/OS
    autoscale-cpu-svcacct-marathon.json #security permissive or strict on Enterprise DC/OS, using service account and private key (private key stored as a secret)

Verify the app is added with the command `$ dcos marathon app list`

## Scaling Modes

#### CPU

In this mode, the system will scale the service up or down when the CPU has been out of range for the number of cycles defined in AS_SCALE_UP_FACTOR (for up) or AS_COOL_DOWN_FACTOR (for down). For AS_MIN_RANGE and AS_MAX_RANGE on multicore containers, the calculation for determining the value is # of CPU * desired CPU utilization percentage = CPU time (e.g. 80 cpu time * 2 cpu = 160 cpu time)

#### MEM

In this mode, the system will scale the service up or down when the Memory has been out of range for the number of cycles defined in AS_SCALE_UP_FACTOR (for up) or AS_COOL_DOWN_FACTOR (for down). For AS_MIN_RANGE and AS_MAX_RANGE on very small containers, remember that Mesos adds 32MB to the container spec for container overhead (namespace and cgroup), so your target percentages should take that into account.  Alternatively, consider using the CPU only scaling mode for containers with very small memory footprints.

#### SQS

In this mode, the system will scale the service up or down when the Queue available message length has been out of range for the number of cycles defined in AS_SCALE_UP_FACTOR (for up) or AS_COOL_DOWN_FACTOR (for down). For the Amazon Web Services (AWS) Simple Queue Service (SQS) scaling mode, the queue length will be determined by the approximate number of visible messages attribute. The ApproximateNumberOfMessages attribute returns the approximate number of visible messages in a queue.

#### AND

In this mode, the system will only scale the service up or down when both CPU and Memory have been out of range for the number of cycles defined in AS_SCALE_UP_FACTOR (for up) or AS_COOL_DOWN_FACTOR (for down). For the MIN_RANGE and MAX_RANGE arguments/env vars, you must pass in a comma-delimited list of values. Values at index[0] will be used for CPU range and values at index[1] will be used for Memory range.

#### OR

In this mode, the system will only scale the service up or down when either CPU or Memory have been out of range for the number of cycles defined in AS_SCALE_UP_FACTOR (for up) or AS_COOL_DOWN_FACTOR (for down). For the MIN_RANGE and MAX_RANGE arguments/env vars, you must pass in a comma-delimited list of values. Values at index[0] will be used for CPU range and values at index[1] will be used for Memory range.

## Extending the autoscaler (adding a new scaling mode)
In order to create a new scaling mode, you must create a new subclass in the modes directory/module and implement all abstract methods (e.g. scale_direction) of the abstract class [AbstractMode](autoscaler/modes/abstractmode.py).

Please note. The scale_direction function **MUST** return one of three values:

- **Scaling mode above thresholds MUST return 1**
- **Scaling mode within thresholds MUST return 0**
- **Scaling mode below thresholds MUST return -1**

An example skeleton is below:
```
class ScaleByExample(AbstractMode):

    def __init__(self, api_client=None, app=None, dimension=None):
        super().__init__(api_client, app, dimension)

    def scale_direction(self):
         try:
            value = self.get_value()
            return super().scale_direction(value)
         except ValueError:
            raise
```

Once the new subclass is created, add the new mode to the MODES dictionary in [Marathon AutoScaler](marathon_autoscaler.py).
```
# Dict defines the different scaling modes available to autoscaler
MODES = {
    'sqs': ScaleBySQS,
    'cpu': ScaleByCPU,
    'mem': ScaleByMemory,
    'and': ScaleByCPUAndMemory,
    'or': ScaleByCPUOrMemory,
    'exp': ScaleByExample
}
```

## Examples
The following examples execute the python application from the command line.

#### (Optional) Only if using username/password or a service account

    export AS_USERID=some-user-id
    export AS_PASSWORD=some-password
    -or-
    export AS_SECRET=dc-os-secret-formatted-json

#### SQS message queue length as autoscale trigger

    export AS_QUEUE_URL=
    export AWS_ACCESS_KEY_ID=
    export AWS_SECRET_ACCESS_KEY=
    export AWS_DEFAULT_REGION=us-east-1

    python marathon_autoscaler.py --dcos-master https://leader.mesos --trigger_mode sqs --autoscale_multiplier 1.5 --max_instances 5 --marathon-app /test/stress-sqs --min_instances 1 --cool_down_factor 4 --scale_up_factor 3 --interval 10 --min_range 2.0 --max_range 10.0

#### CPU as autoscale trigger

    python marathon_autoscaler.py --dcos-master https://leader.mesos --trigger_mode cpu --autoscale_multiplier 1.5 --max_instances 5 --marathon-app /test/stress-cpu --min_instances 1 --cool_down_factor 4 --scale_up_factor 3 --interval 10 --min_range 55.0 --max_range 80.0

#### Memory as autoscale trigger

    python marathon_autoscaler.py --dcos-master https://leader.mesos --trigger_mode mem --autoscale_multiplier 1.5 --max_instances 5 --marathon-app /test/stress-memory --min_instances 1 --cool_down_factor 4 --scale_up_factor 3 --interval 10 --min_range 55.0 --max_range 75.0

#### AND (CPU and Memory) as autoscale trigger

    python marathon_autoscaler.py --dcos-master https://leader.mesos --trigger_mode and --autoscale_multiplier 1.5 --max_instances 5 --marathon-app /test/stress-cpu --min_instances 1 --cool_down_factor 4 --scale_up_factor 3 --interval 10 --min_range 55.0,2.0 --max_range 75.0,8.0

#### OR (CPU or Memory) as autoscale trigger

    python marathon_autoscaler.py --dcos-master https://leader.mesos --trigger_mode or --autoscale_multiplier 1.5 --max_instances 5 --marathon-app /test/stress-cpu --min_instances 1 --cool_down_factor 4 --scale_up_factor 3 --interval 10 --min_range 55.0,10.0 --max_range 75.0,20.0
