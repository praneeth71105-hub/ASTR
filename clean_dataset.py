import os

from utils import create_sample_dataset, normalize_rows, read_csv_rows, write_csv_rows


def clean_dataset(
    input_path: str = "fraudTrain.csv",
    output_path: str = "sample_data.csv",
    rows: int = 100,
) -> str:
    if os.path.exists(input_path):
        rows_data = read_csv_rows(input_path)
    elif os.path.exists(output_path):
        # sample_data.csv already exists — clean it in-place, do not overwrite with random data
        rows_data = read_csv_rows(output_path)
    else:
        rows_data = create_sample_dataset(rows=rows)

    cleaned_rows = normalize_rows(rows_data)[:rows]
    write_csv_rows(output_path, cleaned_rows)
    return output_path


if __name__ == "__main__":
    path = clean_dataset()
    print(f"Cleaned dataset created at: {path}")
