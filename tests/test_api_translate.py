from quillwright.api.translate import translate_estimate


class _FakeAya:
    name = "aya"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, image_path=None):
        # echo a marker so we can assert it was used + which text was sent
        self.calls.append(prompt)
        # pretend-translate: uppercase the quoted source text
        return "TRANSLATED"


def test_translate_estimate_localizes_descriptions_and_labels():
    est = {
        "job_title": "AC repair",
        "line_items": [
            {
                "description": "Dual run capacitor",
                "quantity": 1,
                "unit": "ea",
                "rate": 24.0,
                "subtotal": 24.0,
            }
        ],
        "subtotal": 24.0,
        "tax_rate": 0.13,
        "tax": 3.12,
        "total": 27.12,
    }
    model = _FakeAya()
    out = translate_estimate(est, "Spanish", model)
    # numbers are unchanged (we never translate money)
    assert out["total"] == 27.12
    assert out["line_items"][0]["rate"] == 24.0
    # the description was sent to the model and replaced
    assert out["line_items"][0]["description"] == "TRANSLATED"
    assert model.calls  # the model was actually invoked


def test_translate_to_english_is_a_noop():
    est = {"job_title": "x", "line_items": [], "subtotal": 0, "tax_rate": 0, "tax": 0, "total": 0}
    model = _FakeAya()
    out = translate_estimate(est, "English", model)
    assert out == est
    assert not model.calls  # no translation needed
