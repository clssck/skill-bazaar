"""Tests for analyze_scala._classify_rdd_usage (R1 bucket-aware RDD guidance).

Bucket A (unsupported, manual EWI): .rdd accessor, partition introspection,
mapPartitions/foreachPartition, SparkContext file APIs — no DataFrame equivalent.
Bucket B (convertible): sc.parallelize / sc.emptyRDD and key-based pair ops.
"""

from __future__ import annotations

import analyze_scala as a


def test_rdd_accessor_is_unsupported():
    g = a._classify_rdd_usage("val n = df2.rdd.getNumPartitions")
    assert g["unsupported"] is True
    assert "SPRKCNTSCL1500" in g["fix"]
    assert "Do NOT fabricate" in g["fix"]


def test_partitions_and_mappartitions_unsupported():
    assert a._classify_rdd_usage("df.rdd.partitions.length")["unsupported"] is True
    assert a._classify_rdd_usage("df.rdd.mapPartitions(it => it)")["unsupported"] is True


def test_parallelize_is_convertible():
    g = a._classify_rdd_usage("val rdd = spark.sparkContext.parallelize(data)")
    assert g["unsupported"] is False
    assert "createDataFrame" in g["fix"]
    assert "Tuple1" in g["fix"]  # warns against the wrong form


def test_emptyrdd_is_convertible():
    g = a._classify_rdd_usage("spark.createDataFrame(spark.sparkContext.emptyRDD[Row], schema)")
    assert g["unsupported"] is False
    assert "asJava" in g["fix"]


def test_pairop_is_convertible_with_agg_guidance():
    g = a._classify_rdd_usage(
        "val rdd = spark.sparkContext.parallelize(data)\nval r2 = rdd.reduceByKey(_ + _)"
    )
    assert g["unsupported"] is False
    assert "groupBy" in g["fix"]


def test_unsupported_wins_over_convertible_when_both_present():
    # A block that both parallelizes AND touches .rdd must be treated as manual.
    g = a._classify_rdd_usage(
        "val rdd = spark.sparkContext.parallelize(data)\nprintln(rdd.rdd.getNumPartitions)"
    )
    assert g["unsupported"] is True
