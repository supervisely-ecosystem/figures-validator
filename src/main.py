# coding: utf-8

from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

import supervisely as sly
from supervisely.annotation.json_geometries_map import GET_GEOMETRY_FROM_STR
from supervisely.api.module_api import ApiField

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


class ValidationResponse(BaseModel):
    figure_validations: List[FigureValidationResult]


@server.post("/validate-figures")
async def validate_figures(req: ValidationReq):
    tm = sly.TinyTimer()

    img_height = req.height
    img_width = req.width
    img_size = (img_height, img_width)
    canvas_rect = sly.Rectangle.from_size(img_size)

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

            if shape is sly.Bitmap:
                data = data_json[sly.Bitmap.geometry_name()]["data"]
                origin = data_json[sly.Bitmap.geometry_name()]["origin"]
                mask_data = sly.Bitmap.base64_2_data(data)
                geometry = sly.Bitmap(mask_data, sly.PointLocation(origin[1], origin[0]))

                left = origin[0]
                top = origin[1]
                bottom = top + mask_data.shape[0] - 1
                right = left + mask_data.shape[1] - 1

                # raw mask bbox
                _bbox = sly.Rectangle(top, left, bottom, right)

                # trimmed mask bbox
                geometry_bbox = geometry.to_bbox()

                _corners = [[xy.col, xy.row] for xy in _bbox.corners]
                corners = [[xy.col, xy.row] for xy in geometry_bbox.corners]
                for _xy, xy in zip(_corners, corners):
                    if _xy != xy:  # check if bitmap is trimmed
                        geometry_changed = True
                        break
            else:
                geometry = shape.from_json(data_json)
                geometry_bbox = geometry.to_bbox()

            # check figure is within image bounds
            if canvas_rect.contains(geometry_bbox) is False:
                corners = [
                    pos + str((xy.col, xy.row))
                    for pos, xy in zip(["ltop", "rtop", "rbot", "lbot"], geometry_bbox.corners)
                ]
                raise Exception(
                    f"Figure with corners {corners} is out of image bounds: {img_height}x{img_width}"
                )

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

        sly.logger.debug("Figure validation done.", extra={"durat_msec": tm.get_sec() * 1000.0})
        batch_result.append(figure_validation)

    return ValidationResponse(figure_validations=batch_result)
