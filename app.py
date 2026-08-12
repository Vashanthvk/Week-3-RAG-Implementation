import streamlit as st

from rag import answer_question


# ============================================================
# Page Configuration
# ============================================================

st.set_page_config(
    page_title="Legal Contract Assistant",
    page_icon="⚖️",
    layout="centered"
)


# ============================================================
# Header
# ============================================================

st.title(
    "⚖️ Legal Contract Assistant"
)

st.write(
    "Ask questions about the provided legal contracts."
)


# ============================================================
# Question Input
# ============================================================

question = st.text_input(
    "Enter your legal contract question:"
)


# ============================================================
# Ask Question
# ============================================================

if st.button(
    "Ask Question",
    type="primary"
):

    if not question.strip():

        st.warning(
            "Please enter a question."
        )

    else:

        try:

            with st.spinner(
                "Searching contracts and generating answer..."
            ):

                answer, sources = answer_question(
                    question.strip()
                )

            # ------------------------------------------------
            # Answer
            # ------------------------------------------------

            st.subheader(
                "Answer"
            )

            st.write(
                answer
            )

            # ------------------------------------------------
            # Sources
            # ------------------------------------------------

            if sources:

                st.subheader(
                    "Retrieved Context Sources"
                )

                for source in sources:

                    st.write(
                        f"📄 "
                        f"{source['source']} "
                        f"— Page {source['page']}"
                    )

            else:

                st.info(
                    "No document source was retrieved."
                )

        except Exception as error:

            st.error(
                "Unable to process the question."
            )

            st.caption(
                f"Error: {error}"
            )