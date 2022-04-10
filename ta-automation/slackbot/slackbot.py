import logging
import time
import json
import boto3

from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

bot_token = "xoxb-3352336312436-3359152407141-mz2WXM7JCCE0zC5zEHjenw9p"
signing_token = "28831ea678df078862585c2312cdccb5"


class StepFunctionNotFoundException(Exception):
    ...


# process_before_response must be True when running on FaaS
app = App(
    process_before_response=True,
    token=bot_token,
    signing_secret=signing_token,
)


@app.middleware  # or app.use(log_request)
def log_request(logger, body, next):
    logger.debug(body)
    return next()


def respond_to_slack_within_3_seconds(body, ack):
    #    if body.get("text") is None:
    #        ack(f":x: Usage: {command} (description here)")
    #        return False
    #    else:
    #        title = body["text"]
    ack(f"Invoking TA analysis.  Response will take >30 seconds")


def get_step_function(client):
    # find the TA-analysis step function via tagging
    ta_automation_machine = None
    machines = client.list_state_machines()

    for machine in machines["stateMachines"]:
        tags = client.list_tags_for_resource(resourceArn=machine["stateMachineArn"])

        for tag in tags["tags"]:
            if tag["key"] == "aws:cloudformation:stack-name":
                if tag["value"] == "ta-automation":
                    ta_automation_machine = machine
                    print(
                        f'Found ta-automation step function: {machine["stateMachineArn"]}'
                    )
                    break

    if ta_automation_machine == None:
        raise StepFunctionNotFoundException(
            "Unable to find step function with tag aws:cloudformation:stack-name=ta-automation"
        )

    return ta_automation_machine


def process_request(respond, body):
    client = boto3.client("stepfunctions")
    ta_automation_machine = get_step_function(client)

    job = {
        "jobs": [
            {
                "symbol": "btc-aud",
                "date_from": "2022-01-01T04:16:13+10:00",
                "date_to": "2022-03-30T04:16:13+10:00",
                "ta_algos": [
                    {
                        "awesome-oscillator": {
                            "strategy": "saucer",
                            "direction": "bullish",
                        }
                    },
                    {"stoch": None},
                    {"accumulation-distribution": None},
                ],
                "resolution": "1d",
                "search_period": 20,
                "notify_method": "pushover",
                "notify_recipient": "ucYyQ2tLc9CqDUqGXVpZvKiyuCDx9x",
                "target_ta_confidence": 3,
            }
        ]
    }

    state_machine_invocation = client.start_execution(
        stateMachineArn=ta_automation_machine["stateMachineArn"],
        name=body["trigger_id"],
        input=json.dumps(job),
    )

    finished = False
    while not finished:
        time.sleep(5)
        job_execution = client.describe_execution(
            executionArn=state_machine_invocation["executionArn"]
        )

        if job_execution["status"] == "SUCCEEDED":
            finished = True
            break

    state_machine_output = json.loads(job_execution["output"])

    response_message = (
        f'Finished analysis for {state_machine_output["job"]["symbol"]}:\n'
    )

    for analysis in state_machine_output["ta_analyses"]:
        response_message += f' - {str(list(analysis["ta_algo"].keys())[0])} {analysis["ta_analysis"]["confidence"]} confidence {analysis["graph_url"]}\n'

    respond(response_message)


#
command = "/submit-job"
app.command(command)(ack=respond_to_slack_within_3_seconds, lazy=[process_request])

SlackRequestHandler.clear_all_log_handlers()
logging.basicConfig(format="%(asctime)s %(message)s", level=logging.WARNING)


def lambda_handler(event, context):
    slack_handler = SlackRequestHandler(app=app)
    return slack_handler.handle(event, context)
