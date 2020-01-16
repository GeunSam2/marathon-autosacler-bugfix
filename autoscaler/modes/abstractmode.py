from abc import ABC, abstractmethod
import logging


class AbstractMode(ABC):

    def __init__(self, api_client=None, agent_stats=None, app=None,
                 dimension=None):

        super().__init__()

        self.api_client = api_client
        self.agent_stats = agent_stats
        self.app = app
        self.min_range = 0.0
        self.max_range = 100.0

        if dimension is not None:
            if isinstance(dimension["min"], list):
                self.min_range = dimension["min"][0]
            else:
                self.min_range = dimension["min"]

            if isinstance(dimension["max"], list):
                self.max_range = dimension["max"][0]
            else:
                self.max_range = dimension["max"]

        self.log = logging.getLogger("autoscale")

    @abstractmethod
    def scale_direction(self, value):
        """
        Returns (-1, 0, 1) based on whether the incoming value
        is below (-1), within (0), or above (1) the threshold of
        the scaling mode.
        """
        if value > self.max_range:
            self.log.debug("Scaling mode above max threshold of %s"
                           % self.max_range)
            return 1
        elif value < self.min_range:
            self.log.debug("Scaling mode below min threshold of %s"
                           % self.min_range)
            return -1
        else:
            self.log.debug("Scaling mode within thresholds (min=%s, max=%s)"
                           % (self.min_range, self.max_range))
            return 0
