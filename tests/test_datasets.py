import json
import os

from langchain import LLMChain, OpenAI, PromptTemplate
import pytest
from langfuse import Langfuse
from langfuse.api.client import FintoLangfuse
from langfuse.model import CreateDatasetItemRequest, InitialGeneration
from langfuse.model import CreateDatasetRequest
from tests.api_wrapper import LangfuseAPI


from tests.utils import create_uuid


def test_create_and_get_dataset():
    langfuse = Langfuse(os.environ.get("LF_PK"), os.environ.get("LF_SK"), os.environ.get("HOST"), debug=True)

    name = create_uuid()
    langfuse.create_dataset(CreateDatasetRequest(name=name))
    dataset = langfuse.get_dataset(name)
    assert dataset.name == name


def test_create_dataset_item():
    langfuse = Langfuse(os.environ.get("LF_PK"), os.environ.get("LF_SK"), os.environ.get("HOST"), debug=True)
    name = create_uuid()
    langfuse.create_dataset(CreateDatasetRequest(name=name))

    input = json.dumps({"input": "Hello World"})
    langfuse.create_dataset_item(CreateDatasetItemRequest(dataset_name=name, input=input))

    dataset = langfuse.get_dataset(name)
    assert len(dataset.items) == 1
    assert dataset.items[0].input == input


def test_linking_observation():
    langfuse = Langfuse(os.environ.get("LF_PK"), os.environ.get("LF_SK"), os.environ.get("HOST"), debug=True)

    dataset_name = create_uuid()
    langfuse.create_dataset(CreateDatasetRequest(name=dataset_name))

    input = json.dumps({"input": "Hello World"})
    langfuse.create_dataset_item(CreateDatasetItemRequest(dataset_name=dataset_name, input=input))

    dataset = langfuse.get_dataset(dataset_name)
    assert len(dataset.items) == 1
    assert dataset.items[0].input == input

    run_name = create_uuid()
    generation_id = create_uuid()

    for item in dataset.items:
        generation = langfuse.generation(InitialGeneration(id=generation_id))

        item.link(generation, run_name)

    run = langfuse.get_dataset_run(dataset_name, run_name)

    assert run.name == run_name
    assert len(run.dataset_run_items) == 1
    assert run.dataset_run_items[0].observation_id == generation_id


@pytest.mark.skip(reason="inference cost")
def test_langchain_dataset():
    langfuse = Langfuse(os.environ.get("LF_PK"), os.environ.get("LF_SK"), os.environ.get("HOST"), debug=True)
    dataset_name = create_uuid()
    langfuse.create_dataset(CreateDatasetRequest(name=dataset_name))

    input = json.dumps({"input": "Hello World"})
    langfuse.create_dataset_item(CreateDatasetItemRequest(dataset_name=dataset_name, input=input))

    dataset = langfuse.get_dataset(dataset_name)

    run_name = create_uuid()

    for item in dataset.items:
        handler = item.get_langchain_handler(run_name=run_name)

        llm = OpenAI(openai_api_key=os.environ.get("OPENAI_API_KEY"))
        template = """You are a playwright. Given the title of play, it is your job to write a synopsis for that title.
            Title: {title}
            Playwright: This is a synopsis for the above play:"""

        prompt_template = PromptTemplate(input_variables=["title"], template=template)
        synopsis_chain = LLMChain(llm=llm, prompt=prompt_template)

        synopsis_chain.run("Tragedy at sunset on the beach", callbacks=[handler])

    run = langfuse.get_dataset_run(dataset_name, run_name)

    assert run.name == run_name
    assert len(run.dataset_run_items) == 1
    assert run.dataset_run_items[0].dataset_run_id == run.id

    api = FintoLangfuse(
        username=os.environ.get("LF_PK"), password=os.environ.get("LF_SK"), environment=os.environ.get("HOST")
    )
    api.generations.get()
    trace = api.trace.get(handler.get_trace_id())

    assert len(trace.observations) == 3
    assert trace.observations[1].id == trace.observations[2].parent_observation_id
    assert trace.observations[0].id == trace.observations[1].parent_observation_id
    assert trace.observations[0].parent_observation_id is None