"""Pipeline orchestrator — runs parser steps sequentially."""
from core.logging_config import get_logger
from core.exceptions import PipelineError
from pipeline.state import PipelineState

logger = get_logger('pipeline.runner')

# Step name -> (module_path, class_name)
STEP_REGISTRY = {
    'rss_feed': ('parsers.rss_parser', 'RSSParser'),
    'sct_parse': ('parsers.sct_parser', 'SCTParser'),
    'data_entry': ('parsers.data_entry', 'DataEntryParser'),
    'sql_parse': ('parsers.sql_parser', 'SQLParser'),
    'equity_parse': ('parsers.equity_parser', 'EquityParser'),
    'exercise_parse': ('parsers.exercise_parser', 'ExerciseParser'),
    'pba_parse': ('parsers.pba_parser', 'PBAParser'),
    'dct_parse': ('parsers.dct_parser', 'DCTParser'),
    'send_mail': ('mailer.notifier', 'Notifier'),
}

# Default execution order. DCT runs after PBA, before mail, matching production.
DEFAULT_ORDER = [
    'rss_feed',
    'sct_parse',
    'data_entry',
    'sql_parse',
    'equity_parse',
    'exercise_parse',
    'pba_parse',
    'dct_parse',
    'send_mail',
]


def _load_parser(step_name, db):
    """Dynamically import and instantiate a parser class."""
    if step_name not in STEP_REGISTRY:
        raise PipelineError("Unknown step: {}".format(step_name))
    module_path, class_name = STEP_REGISTRY[step_name]
    import importlib
    module = importlib.import_module(module_path)
    parser_class = getattr(module, class_name)
    return parser_class(db)


class PipelineRunner(object):
    """Orchestrates sequential execution of pipeline steps."""

    def __init__(self, db):
        self.db = db
        self.state = PipelineState(db)
        self.results = {}

    def run_all(self):
        """Run all pipeline steps in order."""
        logger.info("=" * 60)
        logger.info("Starting full pipeline run: %s", self.state.run_group)
        logger.info("=" * 60)

        for step_name in DEFAULT_ORDER:
            # Check stop signal between steps
            import builtins
            if getattr(builtins, '_maya_stop_pipeline', False):
                logger.info("Pipeline stopped by user before step '%s'", step_name)
                return self.results

            success = self.run_step(step_name)
            if not success:
                logger.error("Pipeline stopped at step '%s'", step_name)
                return self.results

        logger.info("=" * 60)
        logger.info("Pipeline completed successfully")
        logger.info("=" * 60)
        return self.results

    def run_step(self, step_name):
        """Run a single pipeline step. Returns True on success."""
        logger.info("-" * 40)
        logger.info("Running step: %s", step_name)
        logger.info("-" * 40)

        self.state.start_step(step_name)
        try:
            parser = _load_parser(step_name, self.db)
            # Give parser access to state so it can report progress
            parser._pipeline_state = self.state
            parser._step_name = step_name
            result = parser.run()
            self.results[step_name] = result
            self.state.complete_step(step_name, result)
            logger.info("Step '%s' result: %s", step_name, result)
            return True
        except Exception as e:
            self.results[step_name] = {'error': str(e)}
            self.state.fail_step(step_name, str(e))
            logger.exception("Step '%s' failed with error", step_name)
            return False

    def run_from(self, start_step):
        """Run pipeline from a specific step onwards."""
        if start_step not in DEFAULT_ORDER:
            raise PipelineError("Unknown step: {}".format(start_step))

        start_idx = DEFAULT_ORDER.index(start_step)
        steps_to_run = DEFAULT_ORDER[start_idx:]

        logger.info("Running pipeline from step '%s' (%d steps)",
                     start_step, len(steps_to_run))

        for step_name in steps_to_run:
            success = self.run_step(step_name)
            if not success:
                logger.error("Pipeline stopped at step '%s'", step_name)
                return self.results

        return self.results

    def run_steps(self, step_names):
        """Run specific pipeline steps in order."""
        for step_name in step_names:
            success = self.run_step(step_name)
            if not success:
                return self.results
        return self.results
