import io
import sys
import subprocess
import streamlit as st
import pandas as pd
import numpy as np
import laspy
import requests

try:
    st.set_page_config(page_title="LAZ Converter", page_icon="📡")
except RuntimeError:
    # Not running under `streamlit run`
    print("This app must be started with: streamlit run streamlit_app.py")
    sys.exit(1)

st.title("📡 LAZ Converter – Convert .laz to CSV or XYZ")
st.write("Upload a `.laz` LiDAR file and download it as `.csv` or `.xyz`.")

uploaded_file = st.file_uploader("Select a LAZ file", type=["laz"])
output_format = st.radio("Choose output format:", ["CSV", "XYZ"])

if "counter" not in st.session_state:
    st.session_state.counter = 0

if st.button("Increment counter"):
    st.session_state.counter += 1

st.write("Counter value (persists across reruns):", st.session_state.counter)

if uploaded_file is not None:
    try:
        with st.spinner("Reading LAZ file..."):
            bytes_data = uploaded_file.read()
            las = laspy.read(io.BytesIO(bytes_data))

        # Ensure coordinates are 1-D arrays even for single-point files
        x = np.atleast_1d(np.asarray(las.x))
        y = np.atleast_1d(np.asarray(las.y))
        z = np.atleast_1d(np.asarray(las.z))

        if not (len(x) == len(y) == len(z)):
            raise ValueError("Coordinate arrays have mismatched lengths")

        st.success(f"Loaded {len(x):,} points successfully ✅")

        if output_format == "CSV":
            df = pd.DataFrame({"X": x, "Y": y, "Z": z})
            csv_bytes = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="📥 Download CSV file",
                data=csv_bytes,
                file_name=uploaded_file.name.replace(".laz", ".csv"),
                mime="text/csv",
            )
        else:
            xyz = np.column_stack((x, y, z))
            xyz_str = "\n".join([f"{a:.3f} {b:.3f} {c:.3f}" for a, b, c in xyz])
            xyz_bytes = xyz_str.encode("utf-8")

            st.download_button(
                label="📥 Download XYZ file",
                data=xyz_bytes,
                file_name=uploaded_file.name.replace(".laz", ".xyz"),
                mime="text/plain",
            )

    except Exception as e:
        msg = str(e)
        # Detect missing LAZ backend and offer an in-app installer
        if "No LazBackend" in msg or "cannot decompress" in msg or "LazBackend" in msg:
            st.error("LAZ backend not available — Streamlit can't decompress .laz data.")
            st.write(
                "Install a LAZ backend such as `lazrs` (recommended) or `laszip`.\n\n"
                "Recommended command:\n```\npython3 -m pip install lazrs\n```"
            )

            if st.button("Install lazrs now"):
                with st.spinner("Installing lazrs..."):
                    try:
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "lazrs"])
                    except Exception as ex:
                        st.error(f"Installation failed: {ex}")
                        st.write("Run the install command in your terminal if this fails.")
                    else:
                        st.success("lazrs installed. Please restart the app (streamlit run streamlit_app.py).")
        else:
            st.error(f"Error converting file: {e}")

else:
    st.info("Please upload a .laz file to start.")

st.write("Or provide a direct URL to a .laz file (S3/HTTP) to let the server fetch it:")
laz_url = st.text_input("LAZ file URL (optional)")

if laz_url:
    auth_type = st.selectbox("Auth type for URL", ["None", "Bearer token", "Basic auth"])
    headers = {}
    auth = None
    if auth_type == "Bearer token":
        token = st.text_input("Bearer token (kept secret)", type="password")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "Basic auth":
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if user or pwd:
            auth = (user, pwd)

    try:
        with st.spinner("Downloading .laz from URL..."):
            r = requests.get(laz_url, headers=headers or None, auth=auth, stream=True, timeout=120, allow_redirects=True)

            if r.status_code != 200:
                st.error(f"HTTP {r.status_code}: {r.reason}")
                st.write(r.text[:1000])
                raise RuntimeError(f"HTTP {r.status_code}")

            # read the whole content (server-side download). detect HTML/error pages early.
            data = r.content
            prefix = data[:8].lower()
            content_type = r.headers.get("content-type", "").lower()

            if (prefix.startswith(b'<!do') or prefix.startswith(b'<html') or
                prefix.startswith(b'<?xml') or 'html' in content_type):
                st.error("URL returned HTML (likely an error/redirect page) instead of a .laz file.")
                st.write(data[:500].decode("utf-8", errors="replace"))
                raise RuntimeError("URL returned HTML")

            las = laspy.read(io.BytesIO(data))

        # Ensure coordinates are 1-D arrays even for single-point files
        x = np.atleast_1d(np.asarray(las.x))
        y = np.atleast_1d(np.asarray(las.y))
        z = np.atleast_1d(np.asarray(las.z))

        if not (len(x) == len(y) == len(z)):
            raise ValueError("Coordinate arrays have mismatched lengths")

        st.success(f"Downloaded and loaded {len(x):,} points")

        if output_format == "CSV":
            df = pd.DataFrame({"X": x, "Y": y, "Z": z})
            csv_bytes = df.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="📥 Download CSV file",
                data=csv_bytes,
                file_name="downloaded_file.csv",
                mime="text/csv",
            )
        else:
            xyz = np.column_stack((x, y, z))
            xyz_str = "\n".join([f"{a:.3f} {b:.3f} {c:.3f}" for a, b, c in xyz])
            xyz_bytes = xyz_str.encode("utf-8")

            st.download_button(
                label="📥 Download XYZ file",
                data=xyz_bytes,
                file_name="downloaded_file.xyz",
                mime="text/plain",
            )

    except requests.HTTPError as he:
        if r.status_code == 401:
            st.error("401 Unauthorized: the URL requires credentials or a presigned URL.")
            st.info("Use a presigned URL (S3) or provide token/username+password above.")
        else:
            st.error(f"HTTP error: {r.status_code} {r.reason}")
    except Exception as e:
        st.error(f"Failed to fetch/parse URL: {e}")
        st.info("Ensure the URL points directly to the .laz file (use presigned S3 URL, add ?dl=1 for Dropbox, or enable public GET).")
