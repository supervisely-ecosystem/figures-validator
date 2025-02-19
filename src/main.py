# coding: utf-8

import uuid
from typing import List, Optional

import supervisely as sly
from fastapi import FastAPI, Request
from pydantic import BaseModel
from supervisely import logger
from supervisely.annotation.json_geometries_map import GET_GEOMETRY_FROM_STR
from supervisely.api.module_api import ApiField
from supervisely.geometry.helpers import geometry_to_polygon

# app = sly.Application()
# server = app.get_server()
app = FastAPI()
server = app


class FigureValidationData(BaseModel):
    area: float
    geometry_bbox: List
    geometry: Optional[dict] = None


class FigureValidationResult(BaseModel):
    data: Optional[FigureValidationData] = None
    error: Optional[str] = None


class ValidationReq(BaseModel):
    height: int
    width: int
    figures: List[dict]
    skipBoundsValidation: Optional[bool] = False


class ValidationResponse(BaseModel):
    figure_validations: List[FigureValidationResult]


class ConversionReq(BaseModel):
    figures: List[dict]


class ConversionResult(BaseModel):
    data: Optional[dict] = None
    error: Optional[str] = None


class ConversionResponse(BaseModel):
    converted_figures: List[ConversionResult]


@server.post("/validate-figures")
def validate_figures(orig_req: Request, req: ValidationReq):
    tm = sly.TinyTimer()

    req_id = orig_req.headers.get("x-request-uid", uuid.uuid4())
    extra_log_meta = {"requestUid": req_id}
    logger.debug("Figure validation started", extra=extra_log_meta)

    img_height = req.height
    img_width = req.width
    img_size = (img_height, img_width)
    canvas_rect = sly.Rectangle.from_size(img_size)
    skip_bounds_validation = req.skipBoundsValidation

    batch_result = []

    for figure in req.figures:
        figure_validation = FigureValidationResult()

        try:
            shape_str = figure[ApiField.GEOMETRY_TYPE]
            data_json = figure[ApiField.GEOMETRY]
            shape = GET_GEOMETRY_FROM_STR(shape_str)
            geometry = None
            geometry_bbox = None
            geometry_changed = False

            if shape in (sly.Bitmap, sly.AlphaMask):
                bitmap_name = sly.Bitmap.geometry_name()
                shape_name = shape.geometry_name()

                data_bitmap: dict = data_json[bitmap_name]
                if data_bitmap is None:
                    raise Exception(f"{shape_name}: {bitmap_name}'s data is None (null).")
                if "data" not in data_bitmap:
                    raise Exception(
                        f"{shape_name}: 'data' field is missing in {bitmap_name}'s data."
                    )
                if "origin" not in data_bitmap:
                    raise Exception(
                        f"{shape_name}: 'origin' field is missing in {bitmap_name}'s data."
                    )

                data = data_bitmap["data"]
                origin = data_bitmap["origin"]
                mask_data = shape.base64_2_data(data)
                geometry = shape(mask_data, sly.PointLocation(origin[1], origin[0]))

                # trimmed mask bbox
                geometry_bbox = geometry.to_bbox()

                if shape is sly.Bitmap:
                    left = origin[0]
                    top = origin[1]
                    bottom = top + mask_data.shape[0] - 1
                    right = left + mask_data.shape[1] - 1

                    # raw mask bbox
                    _bbox = sly.Rectangle(top, left, bottom, right)

                    _corners = [[xy.col, xy.row] for xy in _bbox.corners]
                    corners = [[xy.col, xy.row] for xy in geometry_bbox.corners]
                    for _xy, xy in zip(_corners, corners):
                        if _xy != xy:  # check if bitmap is trimmed
                            geometry_changed = True
                            break
            else:
                data_in_px = shape._to_pixel_coordinate_system_json(data_json, img_size)
                geometry = shape.from_json(data_in_px)
                geometry_bbox = geometry.to_bbox()

            # check figure is within image bounds
            if not skip_bounds_validation:
                if canvas_rect.contains(geometry_bbox) is False:
                    corners = [
                        pos + str((xy.col, xy.row))
                        for pos, xy in zip(["ltop", "rtop", "rbot", "lbot"], geometry_bbox.corners)
                    ]
                    raise Exception(
                        f"Figure with corners {corners} is out of image bounds: {img_height}x{img_width}"
                    )

            # check if there are no contours with less than 3 points in polygon
            if shape == sly.Polygon:
                exterior = data_json["points"]["exterior"]
                interior = data_json["points"]["interior"]

                if len(exterior) < 3:
                    raise Exception("Polygon has exterior contour with less than 3 points.")
                if any(len(contour) < 3 for contour in interior):
                    raise Exception("Polygon contains interior contour with less than 3 points.")

            figure_validation.data = FigureValidationData(
                area=geometry.area,
                geometry_bbox=[
                    geometry_bbox.top,
                    geometry_bbox.left,
                    geometry_bbox.bottom,
                    geometry_bbox.right,
                ],
                geometry=geometry.to_json() if geometry_changed else None,
            )
        except Exception as exc:
            figure_validation.error = str(exc)

        logger.debug(
            "Figure validation finished",
            extra={**extra_log_meta, "responseTime": round(tm.get_sec() * 1000.0)},
        )
        batch_result.append(figure_validation)

    return ValidationResponse(figure_validations=batch_result)


@server.post("/mask-to-poly")
def convert_mask_to_poly(orig_req: Request, req: ConversionReq):
    tm = sly.TinyTimer()
    req_id = orig_req.headers.get("x-request-uid", uuid.uuid4())
    extra_log_meta = {"requestUid": req_id}
    logger.info(f"Start converting {len(req.figures)} masks to polygons", extra=extra_log_meta)

    converted_figures = []

    for figure in req.figures:
        conversion_result = ConversionResult()
        try:
            shape_str = figure[ApiField.GEOMETRY_TYPE]
            shape = GET_GEOMETRY_FROM_STR(shape_str)

            if shape == sly.Bitmap:
                geometry = sly.Bitmap.from_json(figure)
                poly_geometries: List[sly.Polygon] = geometry_to_polygon(geometry)
                if len(poly_geometries) != 1:
                    raise Exception(
                        "Operation canceled: Invalid mask detected. "
                        f"Found {len(poly_geometries)} contours instead of one. "
                        "The mask may have gaps or multiple regions."
                    )
                json_poly = poly_geometries[0].to_json()
                conversion_result.data = json_poly
            else:
                raise Exception(f"Operation canceled: Unsupported geometry type: {shape_str}")

        except Exception as exc:
            conversion_result.error = str(exc)

        converted_figures.append(conversion_result)
        logger.info(
            "Figure conversion completed.",
            extra={**extra_log_meta, "responseTime": round(tm.get_sec() * 1000.0)},
        )
    return ConversionResponse(converted_figures=converted_figures)
