from autoscaler.modes.abstractmode import AbstractMode


class ScaleByMemory(AbstractMode):

    def __init__(self, api_client=None, agent_stats=None, app=None,
                 dimension=None):
        super().__init__(api_client, agent_stats, app, dimension)

    def get_value(self):

        app_mem_values = []

        # Get a dictionary of app taskId and hostId for the marathon app
        app_task_dict = self.app.get_app_details()

        # verify if app has any Marathon task data.
        if not app_task_dict:
            raise ValueError("No marathon app task data found for app %s" % self.app.app_name)

        try:

            for task, agent in app_task_dict.items():
                self.log.info("Inspecting task %s on agent %s",
                              task, agent)

                # Memory usage
                mem_utilization = self.get_mem_usage(task, agent)
                app_mem_values.append(mem_utilization)

        except ValueError:
            raise

        # Normalized data for all tasks into a single value by averaging
        app_avg_mem = (sum(app_mem_values) / len(app_mem_values))
        self.log.info("Current average Memory utilization for app %s = %s",
                      self.app.app_name, app_avg_mem)

        return app_avg_mem

    def scale_direction(self):

        try:
            value = self.get_value()
            return super().scale_direction(value)
        except ValueError:
            raise

    def get_mem_usage(self, task, agent):
        """Calculate memory usage for the task on the given agent
        """
        task_stats = self.agent_stats.get_task_stats(agent, task)

        # RAM usage
        if task_stats is not None:
            mem_rss_bytes = int(task_stats['mem_rss_bytes'])
            mem_limit_bytes = int(task_stats['mem_limit_bytes'])
            if mem_limit_bytes == 0:
                raise ValueError("mem_limit_bytes for task {} agent {} is 0".format(task, agent))

            mem_utilization = 100 * (float(mem_rss_bytes) / float(mem_limit_bytes))

        else:
            mem_rss_bytes = 0
            mem_limit_bytes = 0
            mem_utilization = 0

        self.log.debug("task %s mem_rss_bytes %s mem_utilization %s mem_limit_bytes %s",
                       task, mem_rss_bytes, mem_utilization, mem_limit_bytes)

        return mem_utilization
