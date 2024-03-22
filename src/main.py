# coding: utf-8

import json
import os
from typing import List, Optional

import supervisely as sly
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, root_validator
from supervisely.annotation.json_geometries_map import GET_GEOMETRY_FROM_STR
from supervisely.api.module_api import ApiField

app = sly.Application()
server = app.get_server()


class FigureValidationResult(BaseModel):
    area: float
    figure_height: Optional[int]
    figure_width: Optional[int]
    figure_json: Optional[str]
    error: Optional[str] = None

    @root_validator(pre=True)
    def validate_all(cls, values):
        area = values.get("area")
        if area is not None and area < 0:
            values["error"] = f"Area ({area}) cannot be negative"  # Example
        return values


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

    batch_result = []

    for figure in req.figures:
        shape_str = figure[ApiField.GEOMETRY_TYPE]
        data_json = figure[ApiField.GEOMETRY]
        figure_json = None
        figure_height = None
        figure_width = None
        try:
            shape = GET_GEOMETRY_FROM_STR(shape_str)

            figure = shape.from_json(data_json)
            bbox = figure.to_bbox()
            figure_height = bbox.height
            figure_width = bbox.width
            if shape is sly.Bitmap:
                data = data_json[sly.Bitmap.geometry_name()]["data"]
                origin = data_json[sly.Bitmap.geometry_name()]["origin"]
                _bbox = sly.Bitmap(
                    shape.base64_2_data(data), sly.PointLocation(origin[1], origin[0])
                ).to_bbox()

                _corners = [[xy.col, xy.row] for xy in _bbox.corners]
                corners = [[xy.col, xy.row] for xy in bbox.corners]
                for _xy, xy in zip(_corners, corners):
                    if _xy != xy:  # check if bitmap is trimmed
                        figure_json = json.dumps(figure.to_json())
                        break

            figure_validation = FigureValidationResult(
                area=figure.area,
                figure_height=figure_height,
                figure_width=figure_width,
                figure_json=figure_json,
            )

            # check figure is within image bounds
            canvas_rect = sly.Rectangle.from_size(img_size)
            if canvas_rect.contains(bbox) is False:
                corners = [
                    pos + str((xy.col, xy.row))
                    for pos, xy in zip(["ltop", "rtop", "rbot", "lbot"], bbox.corners)
                ]
                raise Exception(
                    f"Figure with corners {corners} is out of image bounds: {img_height}x{img_width}"
                )
        except Exception as exc:
            figure_validation = FigureValidationResult(
                area=figure.area,
                figure_height=figure_height,
                figure_width=figure_width,
                figure_json=figure_json,
                error=str(exc),
            )

        sly.logger.debug("Figure validation done.", extra={"durat_msec": tm.get_sec() * 1000.0})
        batch_result.append(figure_validation)

    return ValidationResponse(figure_validations=batch_result)
