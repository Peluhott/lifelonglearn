import os
import re

# Must run before anything imports tutor.llm. load_dotenv() doesn't override variables
# that are already set, so a call that slips past the fakes fails instead of spending credits.
os.environ["GEMINI_API_KEY"] = "test-key-not-real"
os.environ["LANGSMITH_TRACING"] = "false"

import pytest

from tutor.schemas import (
    IntakeResult,
    PlannerResult,
    ReviewerResult,
    ReviewQuestion,
    TeacherResult,
)


class FakeLLM:
    """Stands in for tutor.llm.structured: returns a canned answer for whichever schema is asked for."""

    def __init__(self):
        self.calls = []                  # schema of every call, in order
        self.steps = ["step one", "step two"]
        self.image_steps = {"step one"}  # steps whose lesson asks for a picture
        self.error = None                # set to an exception to simulate Gemini failing
        self.teacher_barrier = None      # set to a threading.Barrier to prove teachers run at the same time

    def __call__(self, system, content, schema):
        self.calls.append(schema)
        if self.error:
            raise self.error

        if schema is IntakeResult:
            return IntakeResult(
                task_type="explain_concept",
                target_concept="chain rule",
                confusion_type="unstated",
            )
        if schema is PlannerResult:
            return PlannerResult(
                concept_to_teach="chain rule",
                steps=list(self.steps),
                method="worked examples",
            )
        if schema is TeacherResult:
            if self.teacher_barrier:
                self.teacher_barrier.wait()  # times out (BrokenBarrierError) unless every teacher arrives together
            step = content.split("Step to teach: ")[-1]
            return TeacherResult(
                step=step,
                explanation=f"explanation of {step}",
                image_prompt=f"diagram of {step}" if step in self.image_steps else None,
            )
        if schema is ReviewerResult:
            taught = re.findall(r"^Step: (.*)$", content, re.MULTILINE)
            return ReviewerResult(
                questions=[
                    ReviewQuestion(
                        step=step,
                        question=f"question about {step}?",
                        choices=["right", "wrong 1", "wrong 2", "wrong 3"],
                        correct_answer="right",
                    )
                    for step in taught
                ]
            )
        raise AssertionError(f"FakeLLM has no canned answer for {schema.__name__}")


class FakeImage:
    """Stands in for generate_image: records prompts and returns a fixed file name."""

    def __init__(self):
        self.prompts = []
        self.error = None

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return "fake.png"


# autouse: every test gets both fakes, so no test can reach Gemini by forgetting one
@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr("tutor.llm.structured", fake)
    return fake


@pytest.fixture(autouse=True)
def fake_image(monkeypatch):
    fake = FakeImage()
    # teacher.py does `from tutor.tools.images import generate_image`, so patch the name it holds
    monkeypatch.setattr("tutor.agents.teacher.generate_image", fake)
    return fake
