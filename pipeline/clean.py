"""Build a unified residential sales table from both localities.

Output: data/processed/sales.parquet with one row per arm's-length
residential sale, plus data/processed/parcels_geo.parquet handled in join_geo.
"""

import csv
import io
import json
import zipfile

import pandas as pd

from .config import PROCESSED, RAW, SALES_START


def read_alb_txt(zip_name: str, txt_name: str) -> pd.DataFrame:
    with zipfile.ZipFile(RAW / zip_name) as z, z.open(txt_name) as f:
        text = io.TextIOWrapper(f, encoding="latin-1", newline="")
        rows = list(csv.DictReader(text))
    df = pd.DataFrame(rows)
    return df.replace({"NULL": None, "": None})


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# ---------------------------------------------------------------- city


def clean_cville() -> pd.DataFrame:
    sales = pd.DataFrame(json.load(open(RAW / "cville_sales.json")))
    resid = pd.DataFrame(json.load(open(RAW / "cville_residential.json")))
    base = pd.DataFrame(json.load(open(RAW / "cville_base.json")))
    assess = pd.DataFrame(json.load(open(RAW / "cville_assessments.json")))

    sales["sale_date"] = pd.to_datetime(sales["SaleDate"], unit="ms")
    sales["sale_price"] = num(sales["SaleAmount"])
    sales = sales[(sales["sale_date"] >= SALES_START) & (sales["sale_price"] > 0)]

    # multi-parcel deeds: same book/page covers several parcels -> price is
    # for the bundle, not the home; drop all members
    bp = sales.groupby("BookPage")["ParcelNumber"].transform("nunique")
    sales = sales[(bp == 1) | sales["BookPage"].isna()]
    # keep one record per parcel-date (dupes exist with identical price)
    sales = sales.sort_values("sale_price").drop_duplicates(
        ["ParcelNumber", "sale_date"], keep="last"
    )

    ptype = {
        "Single Family": "detached",
        "Single Family Attached": "attached",
        "Condominium": "condo",
    }
    resid = resid[resid["UseCode"].isin(ptype)].copy()
    resid["ptype"] = resid["UseCode"].map(ptype)
    # a handful of parcels have multiple residential-detail records; keep the
    # largest (main dwelling)
    resid["sqft"] = num(resid["SquareFootageFinishedLiving"])
    resid = resid.sort_values("sqft").drop_duplicates("ParcelNumber", keep="last")

    df = sales.merge(resid, on="ParcelNumber", suffixes=("", "_r"))
    df = df.merge(
        base[["ParcelNumber", "GPIN", "Acreage"]].drop_duplicates("ParcelNumber"),
        on="ParcelNumber",
        how="left",
    )

    # arm's-length screen: price vs current assessment (generous band since
    # older sales predate the current assessment)
    assess["assessed"] = num(assess["TotalValue"])
    df = df.merge(
        assess[["ParcelNumber", "assessed"]].drop_duplicates("ParcelNumber"),
        on="ParcelNumber",
        how="left",
    )
    ratio = df["sale_price"] / df["assessed"]
    df = df[(ratio.between(0.35, 3.0)) | df["assessed"].isna()]

    out = pd.DataFrame(
        {
            "locality": "cville",
            "parcel_id": df["ParcelNumber"],
            "gpin": df["GPIN"].astype(str),
            "sale_price": df["sale_price"],
            "sale_date": df["sale_date"],
            "sqft": df["sqft"],
            "beds": num(df["Bedrooms"]),
            "baths": num(df["FullBathrooms"]).fillna(0)
            + 0.5 * num(df["HalfBathrooms"]).fillna(0),
            "year_built": num(df["YearBuilt"]),
            "stories": num(df["NumberOfStories"]),
            "acreage": num(df["Acreage"]),
            "grade": "cv_" + df["Grade"].str.strip().fillna("NA"),
            "ptype": df["ptype"],
        }
    )
    return out


# ---------------------------------------------------------------- county


def clean_albemarle() -> pd.DataFrame:
    sales = read_alb_txt("alb_sales.zip", "GIS_View_Redacted_VisionSales.txt")
    cards = read_alb_txt("alb_cards.zip", "GIS_CardLevelData_new.txt")
    pinfo = read_alb_txt("alb_parcel_info.zip", "GIS_View_Redacted_ParcelInfo.txt")

    sales["sale_date"] = pd.to_datetime(
        sales["saledate1"], format="%m/%d/%Y", errors="coerce"
    )
    sales["sale_price"] = num(sales["saleprice"])
    sales = sales[
        (sales["validitycode"] == "Valid Improved")
        & (sales["sale_date"] >= SALES_START)
        & (sales["sale_price"] > 0)
    ]
    sales = sales.sort_values("sale_price").drop_duplicates(
        ["mapblolot", "sale_date"], keep="last"
    )

    # residential cards; keep parcels with exactly one dwelling so the sale
    # price maps to one set of attributes
    rc = cards[cards["CardType"] == "R"].copy()
    keep_use = {
        "Single Family",
        "Condo-Res-Garden",
        "Condo-Res-TH",
        "Duplex",
    }
    rc = rc[rc["UseCode"].isin(keep_use)]
    rc = rc[rc.groupby("TMP")["TMP"].transform("size") == 1]

    style = rc["HouseStyle"].fillna("")
    rc["ptype"] = "detached"
    rc.loc[
        style.str.startswith(("TH", "SFA")) | (rc["UseCode"] == "Duplex"),
        "ptype",
    ] = "attached"
    rc.loc[
        style.eq("Condominium") | rc["UseCode"].str.startswith("Condo"),
        "ptype",
    ] = "condo"

    df = sales.merge(rc, left_on="mapblolot", right_on="TMP")
    df = df.merge(
        pinfo[["ParcelID", "GPIN", "LotSize"]].drop_duplicates("ParcelID"),
        left_on="mapblolot",
        right_on="ParcelID",
        how="left",
    )

    grade = (
        df["Grade"].str.split(":").str[0].str.strip().fillna("NA")
    )  # "B-1: B-1 Good Minus Quality" -> "B-1"

    out = pd.DataFrame(
        {
            "locality": "albemarle",
            "parcel_id": df["mapblolot"],
            "gpin": df["GPIN"].astype(str),
            "sale_price": df["sale_price"],
            "sale_date": df["sale_date"],
            "sqft": num(df["FinSqFt"]),
            "beds": num(df["Bedroom"]),
            "baths": num(df["FullBath"]).fillna(0)
            + 0.5 * num(df["HalfBath"]).fillna(0),
            "year_built": num(df["YearBuilt"]),
            "stories": num(df["NumStories"]),
            "acreage": num(df["LotSize"]),
            "grade": "al_" + grade,
            "ptype": df["ptype"],
        }
    )
    return out


# ---------------------------------------------------------------- main


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cv = clean_cville()
    al = clean_albemarle()
    df = pd.concat([cv, al], ignore_index=True)

    n0 = len(df)
    df = df[df["sqft"].between(300, 15000)]
    df = df[df["sale_price"].between(30_000, 10_000_000)]
    ppsf = df["sale_price"] / df["sqft"]
    df = df[ppsf.between(40, 2000)]
    df = df[df["year_built"].between(1700, 2027) | df["year_built"].isna()]

    df.to_parquet(PROCESSED / "sales.parquet", index=False)
    print(f"city {len(cv)}, county {len(al)}, merged {n0} -> filtered {len(df)}")
    print(df.groupby(["locality", "ptype"]).size())
    print(df["sale_date"].agg(["min", "max"]))


if __name__ == "__main__":
    main()
